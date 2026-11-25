-- moveshitsound.spec.luau (kit) — a contact's SOUND and VFX leave the server in the same instant as its Bus event
-- (src/kit/Moves.luau apply): before the victim's reaction clip is loaded and started, the knockback and the knockdown.
-- Found in Studio 2026-11-21 by tests/playtest/kit_integration_arena (2 clients + 1 server): the hit sound was broadcast
-- AFTER the reaction's load, so it reached a client one network send after the hit - 173 ms on a background Studio
-- server - against V4 13.8's A/V offset <= 16.7 ms. The order lives in a Roblox-only function, so this reads the source:
-- in apply, the hit sound / block sound / hit VFX broadcasts come right after the Bus event and the parry / dodge exits,
-- and before every slower step.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local function applyBody(): string
	local src = fs.readFile("src/kit/Moves.luau")
	local body = string.match(src, "\n\tlocal function apply%(.-\n\tend\n")
	assert(body, "src/kit/Moves.luau has no apply function")
	return body
end

local function at(body: string, needle: string): number
	local i = string.find(body, needle, 1, true)
	assert(i, `apply no longer has: {needle}`)
	return i :: number
end

return function()
	test.suite("Moves: the hit's sound and VFX go out with its Bus event", function()
		local body = applyBody()
		test.case("after the Bus event and the parry / dodge exits", function()
			local sound = at(body, "Sfx.broadcast(\n\t\t\t\t\tonHit.sfx")
			check.truthy(sound > at(body, "Bus.publish(string.upper("))
			check.truthy(sound > at(body, 'if o.kind == "dodged" then'))
		end)
		test.case("before the reaction, the knockback, the knockdown and the hit-stop", function()
			local sound = at(body, "Sfx.broadcast(\n\t\t\t\t\tonHit.sfx")
			local block = at(body, 'Sfx.broadcast("SwordBlock", pos)')
			local vfx = at(body, "Vfx.broadcast(onHit.vfx, pos)")
			for _, later in
				{
					'vs.track = playAtMarker(vh, name, "Hit")',
					"knockback(victim, aroot, o.knockback)",
					"Ragdoll.knock(victim",
					"vh:TakeDamage(o.damage)",
					"hitstop(s, o.hitstop)",
				}
			do
				local i = at(body, later)
				check.truthy(sound < i, `the hit sound comes after {later}`)
				check.truthy(block < i, `the block sound comes after {later}`)
				check.truthy(vfx < i, `the hit VFX comes after {later}`)
			end
		end)
	end)
end

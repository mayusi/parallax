-- parryattack.spec.luau — a parry and an attack in ONE frame never give the attack a parry's protection (found by the
-- Studio red-team playtest tests/playtest/dojo_combat_redteam, 2026-11-20: the client sent Defend("parry") and
-- Use("BgM1_1") together; the server opened the parry, then started the move, and for the window's 0.15 s every hit on
-- the attacker resolved "parried" - the opponent stunned, the attack running on). Moves' apply() reads the defender's
-- parry through MovesRules.parryAtContact: a move started at or after the parry closes it.
local frk = require("../frk")
local test, check = frk.test, frk.check

local MovesRules = require("../../../src/kit/MovesRules")

local SLASH = { name = "Slash", damage = 10, stun = 0.4, hitstop = 0.05, knockback = { 0, 0, 10 } }
local T = 1.79e9 -- (the server's clock: Workspace:GetServerTimeNow())

return function()
	test.suite("MovesRules.parryAtContact", function()
		test.case("a parry with no move running stays (the window resolve reads)", function()
			check.equal(MovesRules.parryAtContact(T, nil), T)
			local o = MovesRules.resolve(SLASH, { now = T + 0.1, parryAt = MovesRules.parryAtContact(T, nil) })
			check.equal(o.kind, "parried")
		end)
		test.case("a move started in the same instant as the parry closes it", function()
			check.equal(MovesRules.parryAtContact(T, T), nil)
		end)
		test.case("a move started after the parry closes it: a hit in the window is a HIT", function()
			check.equal(MovesRules.parryAtContact(T, T + 0.001), nil)
			local o = MovesRules.resolve(SLASH, { now = T + 0.1, parryAt = MovesRules.parryAtContact(T, T + 0.001) })
			check.equal(o.kind, "hit")
		end)
		test.case("a move that started before the parry (older) leaves it", function()
			check.equal(MovesRules.parryAtContact(T, T - 0.5), T)
		end)
		test.case("no parry, or a parry that is not a number, is none", function()
			check.equal(MovesRules.parryAtContact(nil, T), nil)
			check.equal(MovesRules.parryAtContact(nil, nil), nil)
			check.equal(MovesRules.parryAtContact((0 / 0) :: any, nil), nil)
			check.equal(MovesRules.parryAtContact("1" :: any, nil), nil)
		end)
	end)
end

-- animpaired.spec.luau — WHEN A PAIRED MOVE BREAKS, AND WHAT EACH BODY DOES THEN (src/kit/AnimPaired; the owner's
-- older list, AN-32): one verdict from the same facts on every machine - a body gone, dead, stunned from outside or
-- moved off the plan; the commit time after which only gone and dead end it; the shared clock (a late observer, a
-- machine that fell behind). The rule only: what a body does in a game is Studio's to show.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local P = require("../../../src/kit/AnimPaired")

local function ok(): P.Facts
	return { present = true, alive = true }
end

return function()
	test.suite("a paired move that can be broken off: the verdict", function()
		local order = { "grabber", "victim" }
		test.case("two whole bodies on their plan: it runs", function()
			check.is_true(P.verdict(nil, 0.4, order, { grabber = ok(), victim = ok() }) == nil)
			check.is_true(
				P.verdict(
					{},
					0.4,
					order,
					{ grabber = ok(), victim = { present = true, alive = true, apart = 0.4, stunned = false } }
				) == nil
			)
		end)
		test.case("a body gone, dead, stunned from outside, moved off the plan: each ends it, named", function()
			local v =
				P.verdict(nil, 0.4, order, { grabber = ok(), victim = { present = false, alive = true } }) :: P.Verdict
			check.is_true(v.reason == "gone" and v.who == "victim" and v.at == 0.4)
			v = P.verdict(nil, 0.4, order, { grabber = ok() }) :: P.Verdict -- (no facts at all for a role: it is gone)
			check.is_true(v.reason == "gone" and v.who == "victim")
			v = P.verdict(nil, 0.4, order, { grabber = { present = true, alive = false }, victim = ok() }) :: P.Verdict
			check.is_true(v.reason == "death" and v.who == "grabber")
			v = P.verdict(
				nil,
				0.4,
				order,
				{ grabber = { present = true, alive = true, stunned = true }, victim = ok() }
			) :: P.Verdict
			check.is_true(v.reason == "stun" and v.who == "grabber")
			v =
				P.verdict(nil, 0.4, order, { grabber = ok(), victim = { present = true, alive = true, apart = 3.5 } }) :: P.Verdict
			check.is_true(v.reason == "apart" and v.who == "victim")
			-- a rule's own distance
			check.is_true(
				P.verdict(
					{ maxApart = 6 },
					0.4,
					order,
					{ grabber = ok(), victim = { present = true, alive = true, apart = 3.5 } }
				) == nil
			)
			-- a rule's distance that is no distance (0, under 0, not a number) is the default: never "always" or "never"
			local whole = { grabber = ok(), victim = { present = true, alive = true, apart = 0.2 } }
			local far = { grabber = ok(), victim = { present = true, alive = true, apart = 50 } }
			for _, bad in { 0, -1, 0 / 0 } do
				check.is_true(P.verdict({ maxApart = bad }, 0.4, order, whole) == nil)
				check.is_true((P.verdict({ maxApart = bad }, 0.4, order, far) :: P.Verdict).reason == "apart")
			end
			-- a distance that is not a number is no distance
			check.is_true(
				P.verdict(nil, 0.4, order, { grabber = ok(), victim = { present = true, alive = true, apart = 0 / 0 } })
					== nil
			)
		end)
		test.case("two things at once: the graver wins, a tie goes to the first of the cast's order", function()
			-- the victim was pushed away AND the grabber died: the death
			local v = P.verdict(nil, 1, order, {
				grabber = { present = true, alive = false },
				victim = { present = true, alive = true, apart = 9 },
			}) :: P.Verdict
			check.is_true(v.reason == "death" and v.who == "grabber")
			-- one gone, one dead: gone
			v = P.verdict(
				nil,
				1,
				order,
				{ grabber = { present = true, alive = false }, victim = { present = false, alive = false } }
			) :: P.Verdict
			check.is_true(v.reason == "gone" and v.who == "victim")
			-- both stunned: the first of the order, whatever order the facts were made in
			v = P.verdict(nil, 1, order, {
				victim = { present = true, alive = true, stunned = true },
				grabber = { present = true, alive = true, stunned = true },
			}) :: P.Verdict
			check.is_true(v.reason == "stun" and v.who == "grabber")
			v = P.verdict(nil, 1, { "victim", "grabber" }, {
				victim = { present = true, alive = true, stunned = true },
				grabber = { present = true, alive = true, stunned = true },
			}) :: P.Verdict
			check.is_true(v.who == "victim")
			-- a dead body's stun is its death
			v =
				P.verdict(nil, 1, order, { grabber = { present = true, alive = false, stunned = true }, victim = ok() }) :: P.Verdict
			check.is_true(v.reason == "death")
		end)
		test.case("past its commit only a body gone or dead ends it", function()
			local rule = { commit = 0.8 }
			local stunned = { grabber = { present = true, alive = true, stunned = true }, victim = ok() }
			local pushed = { grabber = ok(), victim = { present = true, alive = true, apart = 12 } }
			check.is_true((P.verdict(rule, 0.79, order, stunned) :: P.Verdict).reason == "stun")
			check.is_true(P.verdict(rule, 0.8, order, stunned) == nil)
			check.is_true(P.verdict(rule, 1.5, order, pushed) == nil)
			check.is_true(
				(
					P.verdict(
						rule,
						1.5,
						order,
						{ grabber = ok(), victim = { present = true, alive = false } }
					) :: P.Verdict
				).reason == "death"
			)
			check.is_true(
				(
					P.verdict(
						rule,
						1.5,
						order,
						{ grabber = ok(), victim = { present = false, alive = true } }
					) :: P.Verdict
				).reason == "gone"
			)
			-- no commit said: it never commits
			check.is_true((P.verdict({}, 99, order, stunned) :: P.Verdict).reason == "stun")
		end)
		test.case("a grab a stun cannot break, and a finisher whose victim is meant to die", function()
			local stunned = { grabber = { present = true, alive = true, stunned = true }, victim = ok() }
			check.is_true(P.verdict({ stun = false }, 0.2, order, stunned) == nil)
			local killed = { grabber = ok(), victim = { present = true, alive = false } }
			check.is_true(P.verdict({ fatal = { victim = true } }, 0.2, order, killed) == nil)
			-- ... the killer's own death still ends it, and a victim that is GONE does too
			check.is_true(
				(P.verdict(
					{ fatal = { victim = true } },
					0.2,
					order,
					{ grabber = { present = true, alive = false }, victim = ok() }
				) :: P.Verdict).reason == "death"
			)
			check.is_true(
				(P.verdict(
					{ fatal = { victim = true } },
					0.2,
					order,
					{ grabber = ok(), victim = { present = false, alive = false } }
				) :: P.Verdict).reason == "gone"
			)
		end)
	end)

	test.suite("a paired move that can be broken off: what each body does, and the clock", function()
		test.case("the body the break is about and the other are told apart", function()
			check.is_true(P.exits({ reason = "stun", who = "grabber", at = 0.3 }, "grabber") == "stagger")
			check.is_true(P.exits({ reason = "stun", who = "grabber", at = 0.3 }, "victim") == "release")
			check.is_true(P.exits({ reason = "death", who = "victim", at = 0.3 }, "victim") == "fall")
			check.is_true(P.exits({ reason = "death", who = "victim", at = 0.3 }, "grabber") == "release")
			check.is_true(P.exits({ reason = "gone", who = "victim", at = 0.3 }, "victim") == "none")
			check.is_true(P.exits({ reason = "gone", who = "victim", at = 0.3 }, "grabber") == "release")
			check.is_true(P.exits({ reason = "apart", who = "victim", at = 0.3 }, "victim") == "release")
		end)
		test.case("a machine that lost a body stops driving it; whoever owns it goes on", function()
			check.is_true(P.drives({ present = true, alive = true }))
			check.is_true(P.drives({ present = true, alive = true, owned = true }))
			check.is_true(not P.drives({ present = true, alive = true, owned = false }))
			check.is_true(not P.drives({ present = false, alive = true }))
			check.is_true(not P.drives(nil))
			-- (a body another machine owns is still a whole body to the verdict: the move goes on)
			check.is_true(P.verdict(nil, 0.3, { "a" }, { a = { present = true, alive = true, owned = false } }) == nil)
		end)
		test.case("everybody plays the server's time: a small difference stands, a hitch is snapped", function()
			local t, snapped = P.resync(1.00, 1.04)
			check.is_true(t == 1.00 and not snapped)
			t, snapped = P.resync(1.00, 1.45) -- (a machine that froze for 0.45 s)
			check.is_true(t == 1.45 and snapped)
			t, snapped = P.resync(1.30, 1.00) -- (one that ran ahead)
			check.is_true(t == 1.00 and snapped)
			t, snapped = P.resync(1.00, nil) -- (a local scene: no shared clock)
			check.is_true(t == 1.00 and not snapped)
			t, snapped = P.resync(1.00, 0 / 0)
			check.is_true(t == 1.00 and not snapped)
			t, snapped = P.resync(0 / 0, 1.2) -- (a count that is no number is put on the server's)
			check.is_true(t == 1.2 and snapped)
			t, snapped = P.resync(1.00, 1.04, 0.01)
			check.is_true(t == 1.04 and snapped)
			-- two machines a hitch apart end on the same time once both have asked
			local a, b = 2.0, 2.6
			a, b = (P.resync(a, 2.6)), (P.resync(b, 2.6))
			check.is_true(a == b)
		end)
		test.case("a late observer joins where everyone is, or not at all", function()
			check.is_true(P.joinAt(0.7, 2) == 0.7)
			check.is_true(P.joinAt(-0.2, 2) == 0) -- (a clock a little behind the server's)
			check.is_true(P.joinAt(2, 2) == nil and P.joinAt(5, 2) == nil)
			check.is_true(P.joinAt(0 / 0, 2) == nil)
			check.is_true(P.joinAt(0.5, 0 / 0) == nil and P.joinAt(0, 0) == nil) -- (a move with no length)
		end)
	end)

	test.suite("a paired move that can be broken off: the scene player asks the rule", function()
		test.case("the kit's cutscene player reads each body and ends for everyone on a verdict", function()
			local src = fs.readFile("src/kit/Cutscene.luau")
			for _, line in
				{
					'local AnimPaired = require(script.Parent:WaitForChild("AnimPaired"))',
					"breaks: (AnimPaired.Rule | boolean)?,",
					"onBreak: ((verdict: AnimPaired.Verdict, exits: { [string]: string }) -> ())?,",
					"table.sort(order)",
					"alive = a.hum.Health > 0,",
					'stunned = a.model:GetAttribute("KitStunned") == true',
					'a.model:GetAttribute("KitStunnedUntil")',
					"local ok, server = pcall(o.clock)",
					"if o.onStart and not stopped then",
					"r:FireAllClients(name, nil, startedAt)",
					"if current and currentStart == startedAt then",
					"local at = AnimPaired.joinAt(workspace:GetServerTimeNow() - startedAt, tonumber(tl and tl.duration) or 0)",
					"apart = if present and wrote then (a.root.Position - wrote).Magnitude else nil,",
					"local v = AnimPaired.verdict(breakRule, t, order, facts)",
					"exits[a.role] = AnimPaired.exits(v, a.role)",
					'local at, snapped = AnimPaired.resync(t, if ok and type(server) == "number" then server else nil)',
					"a.wrote = a.root.Position",
				}
			do
				check.truthy(string.find(src, line, 1, true) ~= nil)
			end
			-- unsaid, nothing breaks a scene (as before): the rule is only asked when `breaks` is said
			check.truthy(
				string.find(src, 'if type(o.breaks) == "table" then o.breaks elseif o.breaks then {} else nil', 1, true)
					~= nil
			)
		end)
	end)
end

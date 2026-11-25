-- datarules.spec.luau (kit) — saved data's durability (src/kit/DataRules, LIMITATIONS_FIXES_V4 8.3 profile_durability):
-- one server owns a profile, a crashed server's lock goes stale and may be taken, a live one is never stolen and a
-- server that lost it never clears the new owner's; migrations run in order once, a failing one stops the load, a
-- newer save is refused; new template fields reach old saves without overwriting a value; a grant applies once.
local frk = require("../frk")
local test, check = frk.test, frk.check

local DataRules = require("../../../src/kit/DataRules")

return function()
	test.suite("DataRules: the session lock", function()
		test.case("free, ours, stale, held - and the release", function()
			check.equal((DataRules.canLock(nil, "A", 100)), true)
			local l = DataRules.lock("A", 100)
			check.equal((DataRules.canLock(l, "A", 101)), true) -- (ours: a refresh)
			local ok, why = DataRules.canLock(l, "B", 200, 1800)
			check.equal(ok, false)
			check.truthy(string.find(why, "another server", 1, true) ~= nil)
			check.equal((DataRules.canLock(l, "B", 100 + 1800, 1800)), true) -- (stale: A stopped refreshing)
			check.equal(DataRules.release(l, "A"), nil)
			local taken = DataRules.lock("B", 2000)
			check.equal(DataRules.release(taken, "A"), taken) -- (A lost it: B's lock is not A's to clear)
		end)
		test.case("hostile input never locks and never errors", function()
			for _, bad in { { nil, 1 }, { "", 1 }, { "A", 0 / 0 }, { "A", math.huge }, { 5, 1 } } do
				check.equal((DataRules.canLock(nil, bad[1], bad[2])), false)
			end
			check.equal((DataRules.canLock({ job = 3, at = "x" }, "A", 1)), true) -- (a broken lock is no lock)
		end)
		test.case("LOCK_TTL is exactly 1800 seconds", function()
			-- survivor line 15 (1800 -> 1801): constant value must be pinned
			check.equal(DataRules.LOCK_TTL, 1800)
		end)
		test.case("a 64-character job id is accepted (boundary: idOk max=64)", function()
			-- survivor line 25 (<= -> <): #x == max must be valid
			-- survivor line 32 (64 -> 65): idOk called with max=64, a 64-char job must pass
			local job64 = string.rep("x", 64)
			check.equal((DataRules.canLock(nil, job64, 1)), true)
			-- a 65-character job must be rejected (one over the limit)
			local job65 = string.rep("x", 65)
			check.equal((DataRules.canLock(nil, job65, 1)), false)
		end)
		test.case("ttl=0.5 is used directly (not replaced by LOCK_TTL)", function()
			-- survivor line 35 (0 -> 1): (ttl > 0) with ttl=0.5 is true in original, false with mutant
			-- a lock taken at t=0 by A with ttl=0.5: at t=1 it is already stale (1 >= 0.5)
			local l = DataRules.lock("A", 0)
			local ok2, _ = DataRules.canLock(l, "B", 1, 0.5)
			check.equal(ok2, true) -- stale after 0.5 s; with ttl replaced by 1800 it would still be held
		end)
		test.case("a lock with a non-string job field is treated as free (or logic)", function()
			-- survivor line 40 (or -> and): job is not a string AND at IS finite; original: true or false = true (free)
			-- with 'and' mutant: true and false = false (would not be treated as free)
			check.equal((DataRules.canLock({ job = 5, at = 100 }, "A", 200)), true)
			-- job IS a string but at is not finite: original true or true = true (free)
			check.equal((DataRules.canLock({ job = "X", at = "bad" }, "A", 200)), true)
		end)
	end)
	test.suite("DataRules: migrations", function()
		local steps = {
			function(d)
				d.coins = d.coins or 0
				return d
			end,
			function(d)
				d.gems = (d.coins or 0) // 100
				return d
			end,
		}
		test.case("from any saved version to the latest, each step once, the input untouched", function()
			local saved = { coins = 250 }
			local out, n = DataRules.migrate(saved, steps)
			check.equal(n, 2)
			check.equal(out.version, 2)
			check.equal(out.gems, 2)
			check.equal(saved.version, nil)
			local again, n2 = DataRules.migrate(out, steps)
			check.equal(n2, 0)
			check.equal(again.gems, 2)
		end)
		test.case("a failing step stops the load; a newer save is refused (never downgraded)", function()
			local bad = {
				steps[1],
				function()
					error("boom")
				end,
			}
			local out, why = DataRules.migrate({}, bad)
			check.equal(out, nil)
			check.truthy(string.find(tostring(why), "migration 2 failed", 1, true) ~= nil)
			local out2, why2 = DataRules.migrate({ version = 5 }, steps)
			check.equal(out2, nil)
			check.truthy(string.find(tostring(why2), "newer server", 1, true) ~= nil)
			check.equal((DataRules.migrate("x", steps)), nil)
		end)
	end)
	test.suite("DataRules: reconcile and grants", function()
		test.case("new template fields reach old saves; saved values win; lists stay as saved", function()
			local template = { coins = 0, settings = { music = 0.5, sfx = 0.5 }, inventory = { "starter" } }
			local out = DataRules.reconcile({ coins = 40, settings = { music = 0.1 }, inventory = {} }, template)
			check.equal(out.coins, 40)
			check.equal(out.settings.music, 0.1)
			check.equal(out.settings.sfx, 0.5)
			check.equal(#out.inventory, 0) -- (an emptied list is the player's, not missing)
			local fresh = DataRules.reconcile(nil, template)
			fresh.settings.music = 1
			check.equal(template.settings.music, 0.5) -- (copied, never shared)
		end)
		test.case("hostile input (found by kit fuzz) answers, never throws", function()
			local cyclic: any = {}
			cyclic.self = cyclic
			check.equal(type(DataRules.reconcile({ a = 1 }, cyclic)), "table") -- (a cyclic template: no overflow)
			check.equal(DataRules.reconcile({ a = 1 }, nil :: any).a, 1)
			check.equal((DataRules.migrate({}, 3 :: any)), nil)
			check.equal((DataRules.migrate({}, { 5 } :: any)), nil)
			check.equal((DataRules.canLock(nil, string.rep("x", 100000), 1)), false)
			check.equal((DataRules.canLock(nil, "\0", 1)), false)
			check.equal((DataRules.grant(nil, "\0")), false)
		end)
		test.case("reconcile works at depth 16; a 17-level template is capped (MAX_DEPTH=16)", function()
			-- survivor line 101 (16 -> 17): MAX_DEPTH must be 16, not 17
			-- survivor line 107 (> -> >=): depth > MAX_DEPTH; at depth == MAX_DEPTH the original must continue

			-- To trigger reconcileAt recursion (not deepCopy), the data must have matching nested tables
			-- so the elseif branch fires: type(v)=="table" and type(out[k])=="table" and #v==0
			-- build paired data+template: each level has a record sub-table (empty list -> elseif fires)
			local function makePaired(depth: number): (any, any)
				if depth == 0 then
					-- leaf: data has x=42, template adds y=99
					return { x = 42 }, { x = 0, y = 99 }
				end
				local childData, childTmpl = makePaired(depth - 1)
				return { child = childData }, { child = childTmpl }
			end

			-- 16 levels: reconcileAt called with depth 0..15 for each nested level;
			-- the 16th call is at depth 15 (0-indexed), which is not > 16, so it proceeds and
			-- fills y at the leaf. With MAX_DEPTH=17 mutant this also passes.
			-- The critical distinguishing test is for MAX_DEPTH: use 17 levels, where
			-- the guard at depth=16 fires with original (16 > 16 = false: proceeds!),
			-- but with MAX_DEPTH=17 mutant depth=16 is not > 17, so both pass level 16.
			-- For the >= mutant: depth=16 with >= fires, stopping the 16th recursion.

			-- depth-16 test (kills >= mutant on line 107): data and template both 16 levels deep
			-- reconcileAt is called with depth=16 for the innermost record;
			-- original: 16 > 16 = false -> proceeds, y is filled; mutant: 16 >= 16 = true -> stops, y is nil
			local d16, t16 = makePaired(16)
			local out16 = DataRules.reconcile(d16, t16)
			local leaf16: any = out16
			for _ = 1, 16 do
				leaf16 = leaf16.child
			end
			check.equal(leaf16.x, 42) -- (saved value kept)
			check.equal(leaf16.y, 99) -- (template field added at depth 16; >= mutant stops here: y stays nil)

			-- depth-17 test (kills MAX_DEPTH=17 mutant on line 101):
			-- at depth=17 original fires (17 > 16 = true -> stops, y is nil at level 17)
			-- with MAX_DEPTH=17 mutant, depth=17 is not > 17 -> proceeds, y would be filled
			local d17, t17 = makePaired(17)
			local out17 = DataRules.reconcile(d17, t17)
			local leaf17: any = out17
			for _ = 1, 17 do
				leaf17 = leaf17.child
			end
			check.equal(leaf17.x, 42) -- (saved value present either way)
			check.equal(leaf17.y, nil) -- (original stops at depth 17; MAX_DEPTH=17 mutant would fill it)
		end)
		test.case("reconcile increments depth by 1 each level (not 2)", function()
			-- survivor line 126 (depth+1 -> depth+2): with +2 the guard fires sooner
			-- use a 9-deep structure where data has matching nested tables (elseif branch),
			-- so reconcileAt recurses; with +2 the effective depth at level 9 would be
			-- depth = 0 + 2*9 = 18 which is > 16, stopping before the leaf
			local function makePaired2(depth: number): (any, any)
				if depth == 0 then
					return { x = 42 }, { x = 0, y = 99 }
				end
				local childData, childTmpl = makePaired2(depth - 1)
				return { child = childData }, { child = childTmpl }
			end
			local data9, tmpl9 = makePaired2(9)
			local out9 = DataRules.reconcile(data9, tmpl9)
			local leaf9: any = out9
			for _ = 1, 9 do
				leaf9 = leaf9.child
			end
			-- x was saved, y was added from template
			check.equal(leaf9.x, 42)
			check.equal(leaf9.y, 99) -- (with depth+2 mutant, depth hits 18 > 16 at level 9: y stays nil)
		end)
		test.case("a grant applies once; the ledger keeps the last LEDGER ids", function()
			local ok, _, ledger = DataRules.grant(nil, "receipt-1")
			check.equal(ok, true)
			local again, why = DataRules.grant(ledger, "receipt-1")
			check.equal(again, false)
			check.truthy(string.find(why, "duplicate", 1, true) ~= nil)
			for i = 2, DataRules.LEDGER + 5 do
				_, _, ledger = DataRules.grant(ledger, `receipt-{i}`)
			end
			check.equal(#ledger, DataRules.LEDGER)
			check.equal((DataRules.grant(ledger, "")), false)
			check.equal((DataRules.grant(ledger, 7)), false)
		end)

		-- line 16 (64 -> 65): LEDGER constant is exactly 64
		test.case("LEDGER is exactly 64 (not 65)", function()
			-- Pinning the constant: the ledger keeps at most 64 entries.
			check.equal(DataRules.LEDGER, 64)
		end)

		-- line 89 (or -> and): a migration that succeeds but returns a non-table also fails
		test.case("migrate: a step returning a non-table (number) stops the migration (or not and)", function()
			-- Original: not ok OR type(nextData)~="table". If ok=true AND nextData=42: false OR true = true -> fail.
			-- Mutant (and): false AND true = false -> does not fail -> continues with numeric data -> downstream error.
			local badReturn = {
				function(d)
					d.x = 1
					return d
				end,
				function(_)
					return 42 -- returns a number, not a table
				end,
			}
			local out, why = DataRules.migrate({}, badReturn)
			check.equal(out, nil) -- migration must fail (or not and)
			check.truthy(string.find(tostring(why), "migration 2 failed", 1, true) ~= nil)
		end)

		-- line 146 (128 -> 129): grant id max length is 128, not 129
		test.case("grant: a 128-character id is accepted; a 129-character id is rejected (max=128 not 129)", function()
			-- Original: idOk(id, 128) -> #id <= 128 -> a 128-char id passes; 129-char fails.
			-- Mutant (129): idOk(id, 129) -> a 129-char id would pass too.
			local id128 = string.rep("a", 128)
			local ok128 = DataRules.grant(nil, id128)
			check.equal(ok128, true) -- exactly 128 chars: accepted
			local id129 = string.rep("a", 129)
			local ok129 = DataRules.grant(nil, id129)
			check.equal(ok129, false) -- 129 chars: rejected (max=128)
		end)

		-- line 154 (1 -> 2): the ledger removes the FIRST entry (oldest), not the second
		test.case("grant: when the ledger is full the OLDEST entry falls off (remove index 1 not 2)", function()
			-- Fill the ledger exactly to LEDGER entries, then add one more.
			-- Original: table.remove(list, 1) removes the oldest (first) entry.
			-- Mutant: table.remove(list, 2) removes the second entry (the first oldest stays).
			-- After overflow, check that the first receipt ("r-1") is gone (original) or still there (mutant).
			local ledger: any = nil
			for i = 1, DataRules.LEDGER do
				local _, _, l = DataRules.grant(ledger, `r-{i}`)
				ledger = l
			end
			check.equal(#ledger, DataRules.LEDGER) -- full
			-- add one more: causes the oldest to fall off
			local _, _, ledger2 = DataRules.grant(ledger, "r-new")
			check.equal(#ledger2, DataRules.LEDGER) -- still full, oldest dropped
			-- "r-1" must be gone (original: remove(1)); with mutant remove(2): "r-1" stays at index 1
			local hasR1 = false
			for _, v in ledger2 do
				if v == "r-1" then
					hasR1 = true
				end
			end
			check.equal(hasR1, false) -- r-1 must have been evicted (remove index 1 = oldest)
		end)
	end)
end

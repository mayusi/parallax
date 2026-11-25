-- ambience.spec.luau — AmbienceRules (src/kit): where each zone kind is present, the beds' crossfade volumes, scatter
-- chance / timing / placement, hostile specs; and SampleRegion's real generated ambience answers sensibly.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Rules = require("../../../src/kit/AmbienceRules")

local SPEC = {
	beds = { open = "bed_meadow", forest = "bed_forest", water = "bed_lake", stone = "bed_castle" },
	volume = { open = 0.8 },
	zones = {
		{ kind = "forest", x = 0, z = 0, r = 50, fade = 20 },
		{ kind = "water", x = 200, z = 0, r = 40, fade = 0 },
	},
	scatter = {
		{
			sound = "bird_chirp",
			kinds = { "open", "forest" },
			every = { 3, 9 },
			distance = { 20, 70 },
			height = { 6, 18 },
		},
	},
}

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-9
end

return function()
	test.suite("AmbienceRules", function()
		test.case("inside a zone its kind is fully present; it fades over its fade; open is what is left", function()
			local p = Rules.presence(SPEC, 10, 0)
			check.equal(p.forest, 1)
			check.equal(p.open, 0)
			local edge = Rules.presence(SPEC, 60, 0) -- (10 studs into a 20-stud fade)
			check.is_true(near(edge.forest, 0.5))
			check.is_true(near(edge.open, 0.5))
			local far = Rules.presence(SPEC, -500, 300)
			check.equal(far.forest, 0)
			check.equal(far.open, 1)
			check.equal(Rules.presence(SPEC, 241, 0).water, 0) -- (no fade: a hard edge)
		end)
		test.case("the beds crossfade with the kinds, each at its kind's volume", function()
			local b = Rules.beds(SPEC, 60, 0)
			check.is_true(near(b.bed_forest, 0.5))
			check.is_true(near(b.bed_meadow, 0.4)) -- (open 0.5 x volume 0.8)
			check.equal(b.bed_lake, 0)
			local inLake = Rules.beds(SPEC, 200, 0)
			check.equal(inLake.bed_lake, 1)
			check.equal(inLake.bed_meadow, 0)
		end)
		test.case("scatter: chance from its kinds, the next time inside 'every', a place in its ranges", function()
			local rule = SPEC.scatter[1]
			check.equal(Rules.chance(rule, Rules.presence(SPEC, 200, 0)), 0) -- (in the lake: no birds)
			check.equal(Rules.chance(rule, Rules.presence(SPEC, 0, 0)), 1)
			check.equal(Rules.nextAt(rule, 100, 0), 103)
			check.equal(Rules.nextAt(rule, 100, 1), 109)
			local dx, dy, dz = Rules.offset(rule, 0, 0.5, 1)
			check.is_true(near(dx, 45) and near(dz, 0))
			check.equal(dy, 18)
		end)
		test.case("hostile specs and points never crash and never go silent everywhere", function()
			for _, bad in { nil, 5, "x", {}, { zones = 5 }, { zones = { { kind = "lava", x = 0, z = 0, r = 10 } } } } do
				local p = Rules.presence(bad, 0, 0)
				check.equal(p.open, 1)
				Rules.beds(bad, 0, 0)
			end
			check.equal(Rules.presence(SPEC, 0 / 0, 0).open, 1)
			check.equal(Rules.presence({ zones = { { kind = "forest", x = 0 / 0, z = 0, r = 10 } } }, 0, 0).forest, 0)
			check.equal(Rules.chance(nil, {}), 0)
			check.equal(Rules.nextAt({ every = { 0, 0 } }, 10, 0.5), 10.5) -- (never sooner than 0.5 s)
			check.equal(Rules.nextAt({ every = { 9, 3 } }, 0, 0), 3) -- (a reversed range still works)
			local dx, dy = Rules.offset(nil, 0, 0, 0)
			check.equal(dx, 40)
			check.equal(dy, 8)
		end)
		test.case("presence: a zone with r=NaN is skipped; a point just past a no-fade zone has w=0", function()
			-- zone with r=NaN: finite(r) is false, the whole zone is skipped (and -> or would let it through with finite x and z)
			local spec2 = { zones = { { kind = "forest", x = 0, z = 0, r = 0 / 0 } } }
			check.equal(Rules.presence(spec2, 0, 0).forest, 0)
			-- a point 0.5 studs past a no-fade zone boundary is NOT in the zone (default fade=0 → hard edge)
			-- if fade defaulted to 1 (mutant), this point would have w = clamp(1-0.5/1) = 0.5
			local spec3 = { zones = { { kind = "forest", x = 0, z = 0, r = 10 } } } -- (no fade field)
			local p = Rules.presence(spec3, 10.5, 0) -- (d=10.5 > r=10, fade=0: should be 0)
			check.equal(p.forest, 0) -- (no fade: hard boundary)
		end)
		test.case("presence: distance uses ^2 along both axes; a point in the fade band along z also fades", function()
			-- tests the z-axis exponent too: a point at (0, 60) is in the forest fade band (d=60, r=50, fade=20)
			local edgeZ = Rules.presence(SPEC, 0, 60) -- (along the z axis, same distance as (60, 0))
			check.is_true(math.abs(edgeZ.forest - 0.5) < 1e-9) -- d=60, same as (60,0): 0.5
			-- also check with a zone not at the origin to test both axes
			local spec2 = { zones = { { kind = "forest", x = 0, z = 0, r = 5, fade = 10 } } }
			local p = Rules.presence(spec2, 0, 10) -- along z: d=10; with ^2: (10-5)/10=0.5; with ^3: d≈31.6, out
			check.is_true(p.forest > 0 and p.forest < 1) -- in the fade band with correct distance
		end)
		test.case("windScale: not-windy kinds always return 1; windy at wind=0 returns 0.55", function()
			-- a kind not in the windy list returns 1 (mutant: 2)
			local v1 = Rules.windScale({}, "forest", 10) -- forest not in default {"open","stone"}
			check.equal(v1, 1)
			-- a windy kind at wind=0: 0.55 + 0.45 * 0 = 0.55 (mutant clamp(0/14,1,1)=1 → 1.0)
			local v2 = Rules.windScale({}, "open", 0)
			check.is_true(math.abs(v2 - 0.55) < 1e-9)
			-- wind=WIND_FULL: 0.55 + 0.45*1 = 1.0
			local v3 = Rules.windScale({}, "open", Rules.WIND_FULL)
			check.is_true(math.abs(v3 - 1.0) < 1e-9)
			-- a table spec with windy=nil uses the default {"open","stone"}; "water" is not in that
			local v4 = Rules.windScale({ windy = nil }, "water", 10)
			check.equal(v4, 1)
		end)
		test.case("inHours: a finite hour outside the range returns false (not early-returned true)", function()
			-- hour=10, range={20, 22} (non-wrap): 10 < 20 → not in hours → returns false
			-- mutant 'drop not': finite(10)=true → early-returns true (wrong)
			check.is_false(Rules.inHours({ 20, 22 }, 10))
			-- hour=21: inside (21 >= 20 and 21 < 22) → true
			check.is_true(Rules.inHours({ 20, 22 }, 21))
			-- hour=22: at the right boundary: 22 >= 22 is true but 22 < 22 is false → not in hours
			check.is_false(Rules.inHours({ 20, 22 }, 22))
			-- a range with one NaN coordinate: the guard fires via `not finite(range[2])`
			-- (or->and mutant would need BOTH range[1] AND range[2] to be non-finite to fire the guard)
			check.is_true(Rules.inHours({ 20, 0 / 0 }, 10)) -- (NaN range[2]: guard fires → returns true)
			-- range[1]=NaN: guard fires via not finite(range[1]) (kills the 'or->and' mutant on 2nd or of line 72)
			-- original (or): not finite(range[1]) = true -> returns true
			-- 2nd-or mutant (and): type({...})~="table" is false AND not finite(NaN) -> false and true = false; guard bypassed
			--   then from=NaN%24=NaN, to=5; from<=to is false; h>=NaN or h<5 -> false or false = false (wrong)
			check.is_true(Rules.inHours({ 0 / 0, 5 }, 10)) -- (NaN range[1]: guard fires → returns true)
		end)
		test.case("inHours: % 24 is used (not % 25); hour=25 wraps to 1 (not 0)", function()
			-- hour=25 % 24 = 1; hour=25 % 25 = 0 (mutant); range {1, 2}: h=1 is in [1,2), h=0 is not
			check.is_true(Rules.inHours({ 1, 2 }, 25)) -- 25 % 24 = 1: in [1,2) → true
			-- also check range wrap: night range [22, 2], hour=25 (h=1 < 2: in hours)
			check.is_true(Rules.inHours({ 22, 2 }, 25)) -- 1 < 2: in the night wrap
			-- range {20, 5}, hour=24: 24%24=0, 0<5 → in hours
			check.is_true(Rules.inHours({ 20, 5 }, 24))
			check.is_false(Rules.inHours({ 20, 5 }, 10))
		end)
		test.case("inHours non-wrap: h < from is not in hours (and not or)", function()
			-- range [8, 20], h=5: h >= from = false, h < to = true
			-- original (and): false and true = false (not in hours)
			-- mutant (or): false or true = true (wrong)
			check.is_false(Rules.inHours({ 8, 20 }, 5)) -- 5 < from=8: not in hours
			check.is_true(Rules.inHours({ 8, 20 }, 8)) -- boundary: 8 >= 8: in hours
			check.is_false(Rules.inHours({ 8, 20 }, 20)) -- boundary: 20 < 20 is false: not in hours
		end)
		test.case("inHours wrap: h < to BUT h < from means not in hours (or not and)", function()
			-- wrapped range [22, 6]: in hours if h >= 22 OR h < 6
			-- mutant (and): h >= 22 AND h < 6 (impossible except never): nothing is in hours
			check.is_true(Rules.inHours({ 22, 6 }, 23)) -- 23 >= 22: in hours
			check.is_true(Rules.inHours({ 22, 6 }, 2)) -- 2 < 6: in hours
			check.is_false(Rules.inHours({ 22, 6 }, 10)) -- neither condition
		end)
		test.case("offset: angle uses 2*pi, not 3*pi; ra=0.25 gives a right-angle direction", function()
			-- ra=0.25: angle = 0.25 * 2 * pi = pi/2; cos(pi/2) ≈ 0, sin(pi/2) ≈ 1
			-- with 3*pi: angle = 0.25 * 3 * pi = 0.75*pi; cos ≈ -0.707, clearly different
			local rule = { distance = { 10, 10 }, height = { 5, 5 } } -- fixed distance=10
			local dx, _, dz = Rules.offset(rule, 0.25, 0.5, 0.5) -- ra=0.25, rd=0.5 → d=10
			check.is_true(math.abs(dx) < 0.01) -- cos(pi/2) ≈ 0
			check.is_true(math.abs(dz - 10) < 0.01) -- sin(pi/2) ≈ 1 → dz = 10
		end)
		test.case(
			"SampleRegion's generated ambience: the lake is water, the keep is stone, the far meadow is open",
			function()
				local path = "games/SampleRegion/src/shared/SampleRegionAmbience.json"
				if not fs.isFile(path) then
					return -- (an installed kit without the SampleRegion game)
				end
				local spec = serde.decode("json", fs.readFile(path))
				check.equal(Rules.presence(spec, 215, 215).water, 1)
				check.equal(Rules.presence(spec, 60, -318).stone, 1)
				check.equal(Rules.presence(spec, 0, 0).open, 1)
				local b = Rules.beds(spec, 60, -318)
				check.is_true(b.bed_castle > 0.8)
			end
		)
		test.case("presence: fade=0.5 (> 0 but <= 1) is used; a point past the boundary fades correctly", function()
			-- kills the '> 0 -> > 1' mutant on line 27: fade=0.5 satisfies > 0 but not > 1
			-- original: fade=0.5; w = clamp(1 - 0.3/0.5, 0, 1) = 0.4
			-- mutant (zone.fade > 1 is false): fade=0 -> w=0 (hard edge)
			local spec4 = { zones = { { kind = "forest", x = 0, z = 0, r = 10, fade = 0.5 } } }
			local p4 = Rules.presence(spec4, 10.3, 0) -- d=10.3, inside the 0.5-stud fade band
			check.is_true(p4.forest > 0 and p4.forest < 1) -- fading, not hard-edge zero
			check.is_true(math.abs(p4.forest - 0.4) < 1e-9) -- exact: 1 - 0.3/0.5 = 0.4
		end)
		test.case("inHours: an infinite hour fires the guard; a table range with finite values does not", function()
			-- kills the 'or -> and' mutant on line 72 (first or): needs not finite(hour)=true with range a table
			-- original (or): not finite(math.huge) = true -> returns true immediately
			-- mutant (and): true AND type({1,2}) ~= "table" = true AND false = false; then range[1]/[2] finite ->
			--   no early return; h = math.huge % 24 = NaN; NaN >= 1 = false -> returns false
			check.is_true(Rules.inHours({ 1, 2 }, math.huge)) -- not finite(math.huge): original=true, mutant=false
			check.is_true(Rules.inHours({ 1, 2 }, -math.huge)) -- -inf: same guard
		end)
		test.case("inHours: range[2]=24 wraps to 0 with %24; range {0,24} is empty with %24 not %25", function()
			-- kills the '24 -> 25' mutant on line 75 targeting range[2]%24:
			-- original: to = 24 % 24 = 0; range [0,0): 12 >= 0 and 12 < 0 = false
			-- mutant: to = 24 % 25 = 24; range [0,24): 12 >= 0 and 12 < 24 = true
			check.is_false(Rules.inHours({ 0, 24 }, 12)) -- (original: to=0, empty interval → false; mutant: to=24 → true)
		end)
		test.case("inHours: range[1]=25 wraps to 1 with %24; {25,2} includes hour=1 but not hour=0", function()
			-- kills the '24 -> 25' mutant on line 75 targeting range[1]%24:
			-- original: from = 25 % 24 = 1; {1,2}: 0 >= 1 = false → false
			-- mutant (from=25%25=0): from=0, to=2, h=0 → 0>=0 and 0<2 = true → true; different!
			check.is_false(Rules.inHours({ 25, 2 }, 0)) -- from=25%24=1, h=0: not in [1,2) → false; mutant: from=0 → true
			check.is_true(Rules.inHours({ 25, 2 }, 1)) -- h=1: in [1,2) → true (both original and mutant agree)
		end)
	end)

	test.suite("AmbienceRules boundary kills", function()
		-- line 17 (0 -> 1): presence() with no matching zones gives zero forest/water/stone (accumulator starts at 0)
		test.case("presence: no zones gives zero forest and water (non-open kinds start at 0 not 1)", function()
			-- Original: out = { open=0, forest=0, water=0, stone=0 }.
			-- With mutant =1: out = { open=1, forest=1, water=1, stone=1 }.
			-- open = 1 - strongest = 1 - 0 = 1 either way (no change for open).
			-- But forest/water/stone stay at their initial value since no zones match.
			local emptySpec = { zones = {} }
			local p = Rules.presence(emptySpec, 999, 999)
			check.equal(p.forest, 0) -- no forest zone: forest presence must be 0 (mutant: starts at 1 -> stays 1)
			check.equal(p.water, 0)
			check.equal(p.stone, 0)
		end)

		-- line 29 (<= -> <): a point at exactly the radius gets weight 1
		test.case("presence: a point exactly at the zone's radius gets full weight (d <= r not d < r)", function()
			-- Original: d <= r -> true at d==r -> w=1. Mutant: d < r -> false at d==r -> goes to elseif.
			-- Need a zone at (0,0) with r=10 and a point at (10, 0): d=10 exactly.
			-- zone.kind must be a non-open kind (open is excluded on line 24)
			local spec = { zones = { { x = 0, z = 0, r = 10, kind = "forest" } } }
			local p = Rules.presence(spec, 10, 0) -- d = sqrt(10^2+0^2) = 10 exactly = r
			-- original: d<=r true -> w=1 -> forest presence = 1; mutant d<r false -> elseif fade>0: fade=0 -> w=0
			check.equal(p.forest, 1) -- weight=1 at the boundary (kills <= -> <)
		end)

		-- line 29 (1 -> 2): the weight for d<=r is 1, not 2
		test.case("presence: a point inside the zone has weight exactly 1 (not 2)", function()
			-- Original: `if d <= r then 1`. Mutant: `if d <= r then 2`.
			-- A forest zone: w=1 -> forest presence=1; with mutant w=2 -> strongest=2 -> open=1-2=-1 (clamped 0).
			local spec = { zones = { { x = 0, z = 0, r = 50, kind = "forest" } } }
			local p = Rules.presence(spec, 0, 0) -- d=0: deep inside, weight=1 (original) or 2 (mutant)
			check.equal(p.forest, 1) -- forest presence at centre must be exactly 1, not 2
		end)

		-- line 46 (== -> ~=): windScale uses a table windy spec
		test.case("windScale: spec.windy as a table controls which kinds scale (== not ~=)", function()
			-- Original: type(spec.windy) == "table" -> true when windy IS a table -> uses it.
			-- Mutant (~=): type(spec.windy) ~= "table" -> false when windy IS a table -> falls back to { open, stone }.
			-- Use spec.windy = { "forest" }: original uses { "forest" }; mutant uses { "open", "stone" }.
			-- Wind=14 (full). Check: "forest" kind with { "forest" } spec: table.find -> found -> scales.
			-- With mutant { "open", "stone" }: "forest" not found -> returns 1 (no scale, constant).
			-- original: "water" in { "water" } -> found -> 0.55+0.45*0.5=0.775 (wind=7, half of WIND_FULL=14)
			-- mutant (~=): uses default { "open","stone" } -> "water" not found -> returns 1. These differ!
			local spec = { windy = { "water" } }
			local waterScale = Rules.windScale(spec, "water", 7)
			check.truthy(math.abs(waterScale - 0.775) < 1e-9) -- custom windy: water found -> partial scale
			local openScale2 = Rules.windScale(spec, "open", 7)
			check.equal(openScale2, 1) -- open not in { "water" }: no scale (original); mutant: "open" in defaults -> scaled
		end)

		-- line 50 (1 -> 2): windScale clamp upper is 1, not 2
		test.case("windScale: a wind above WIND_FULL is clamped to 1 (not 2)", function()
			-- wind = 2 * WIND_FULL = 28: clamp(28/14, 0, 1) = 1. With clamp upper=2: clamp(28/14, 0, 2) = 2.
			-- result: original 0.55+0.45*1 = 1.0; mutant 0.55+0.45*2 = 1.45.
			local s = Rules.windScale({ windy = { "open" } }, "open", 28) -- 2x WIND_FULL
			check.truthy(math.abs(s - 1.0) < 1e-9) -- clamped to 1; with upper=2 would give 1.45
		end)

		-- line 63 (2 -> 3): beds() volume clamp upper is 2, not 3
		test.case("beds: a volume > 2 is clamped to 2 (not 3)", function()
			-- volume[kind] = 3: original clamp(3, 0, 2) = 2. Mutant clamp(3, 0, 3) = 3.
			-- beds() calls presence() internally. The "open" kind always has some presence (1 - strongest).
			-- Use a spec with no non-open zones: open presence = 1; bed "ambient_open" with volume=3.
			local spec = {
				zones = {},
				beds = { open = "ambient_open" },
				volume = { open = 3 }, -- over the max of 2
			}
			local b = Rules.beds(spec, 0, 0)
			check.truthy(math.abs(b.ambient_open - 2) < 1e-9) -- clamped to 2; mutant gives 3
		end)

		-- line 79 (>= -> >) and (< -> <=): inHours non-wrapping boundary
		test.case(
			"inHours: exactly at 'from' is included (>= not >); exactly at 'to' is excluded (< not <=)",
			function()
				-- Original: h >= from and h < to.
				-- h = from: >= true -> included. With > mutant: > false -> excluded.
				check.is_true(Rules.inHours({ 8, 18 }, 8)) -- h == from: included
				-- h = to: original h < to -> false -> excluded. With <= mutant: h <= to -> true -> included.
				check.is_false(Rules.inHours({ 8, 18 }, 18)) -- h == to: excluded
			end
		)

		-- line 104 (1 -> 2): between() clamp roll to [0,1] not [0,2]
		test.case("between: roll > 1 is clamped to 1 (not 2)", function()
			-- roll=1.5: original clamp(1.5, 0, 1) = 1 -> result = lo + (hi-lo)*1 = hi.
			-- Mutant: clamp(1.5, 0, 2) = 1.5 -> result = lo + (hi-lo)*1.5 (over hi).
			-- Range {2, 10}: lo=2, hi=10. Roll=1.5: original gives 10; mutant gives 2+8*1.5=14.
			local d = Rules.nextAt({ every = { 2, 10 } }, 0, 1.5) -- nextAt uses between()
			-- result: 0 + max(0.5, between({2,10}, 1.5, 10)) = max(0.5, lo+(hi-lo)*roll).
			-- Original roll clamped to 1: 2+(10-2)*1=10. nextAt = 0 + max(0.5, 10) = 10.
			-- Mutant roll clamped to 2: 2+8*1.5=14. nextAt = 0 + max(0.5, 14) = 14.
			check.truthy(math.abs(d - 10) < 1e-9) -- roll=1.5 clamped to 1 -> result = 10 not 14
		end)
	end)
end

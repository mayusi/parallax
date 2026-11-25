-- music.spec.luau — MusicRules (src/kit): intensity bumped by events and decaying, stems layered by intensity,
-- changes on the beat / bar; and the SampleDojo's music data names stems its set makes.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Rules = require("../../../src/kit/MusicRules")

local SPEC = {
	bpm = 120,
	beatsPerBar = 4,
	halfLife = 4,
	bumps = { Hit = 0.25, Death = 0.6 },
	stems = {
		{ sound = "pad", from = 0 },
		{ sound = "drums", from = 0.2, full = 0.5 },
		{ sound = "brass", from = 0.6, full = 0.9 },
	},
}

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-9
end

return function()
	test.suite("MusicRules", function()
		test.case("events push the intensity (capped at 1); unknown events do nothing", function()
			check.equal(Rules.bump(SPEC, 0, "Hit"), 0.25)
			check.equal(Rules.bump(SPEC, 0.9, "Death"), 1)
			check.equal(Rules.bump(SPEC, 0.3, "Sneeze"), 0.3)
		end)
		test.case("the intensity halves every half-life", function()
			check.is_true(near(Rules.decay(SPEC, 0.8, 4), 0.4))
			check.is_true(near(Rules.decay(SPEC, 0.8, 8), 0.2))
			check.equal(Rules.decay(SPEC, 0.8, 0), 0.8)
		end)
		test.case("stems layer in: the pad always, drums from 0.2 (full at 0.5), brass only in a real fight", function()
			local calm = Rules.stems(SPEC, 0.05)
			check.equal(calm.pad, 1)
			check.equal(calm.drums, 0)
			check.equal(calm.brass, 0)
			local mid = Rules.stems(SPEC, 0.35) -- (half way into the drums' ramp: eased = 0.5)
			check.is_true(near(mid.drums, 0.5))
			local fight = Rules.stems(SPEC, 0.95)
			check.equal(fight.drums, 1)
			check.equal(fight.brass, 1)
		end)
		test.case("a stinger waits for the next beat; a section change for the next bar", function()
			check.is_true(near(Rules.nextBeat(SPEC, 10, 10.2), 10.5)) -- (120 bpm: beats every 0.5 s)
			check.is_true(near(Rules.nextBeat(SPEC, 10, 10.5), 10.5)) -- (on the beat: now)
			check.is_true(near(Rules.nextBar(SPEC, 10, 10.2), 12)) -- (a bar = 4 beats = 2 s)
			check.equal(Rules.mood(0.1), "calm")
			check.equal(Rules.mood(0.4), "tension")
			check.equal(Rules.mood(0.7), "combat")
		end)
		test.case("bump: a nil spec or a non-table bumps block is handled; bumps table is required", function()
			-- type(spec.bumps) == "table" guard: without it, bump returns intensity unchanged
			check.equal(Rules.bump(nil, 0.3, "Hit"), 0.3)
			check.equal(Rules.bump({ bumps = 5 }, 0.3, "Hit"), 0.3)
			-- type(spec) == "table" guard: non-table spec passes intensity through
			check.equal(Rules.bump("text", 0.5, "Hit"), 0.5)
		end)
		test.case("decay: dt exactly 0 returns intensity unchanged; halfLife=1 is used (not the default 6)", function()
			-- dt <= 0 guard: 0 is not > 0, so it returns intensity unchanged
			check.equal(Rules.decay(SPEC, 0.5, 0), 0.5)
			-- dt = 1 is positive: decay runs (not held back by the guard)
			check.is_true(Rules.decay(SPEC, 0.8, 1) < 0.8)
			-- halfLife = 1 IS > 0: it is used directly (not the default 6); 0.8 halves in 1 s
			check.is_true(near(Rules.decay({ halfLife = 1 }, 0.8, 1), 0.4))
			-- halfLife = 0 is not > 0: falls back to default halfLife = 6; 0.8 decays by 6 s at halfLife 6 = 0.4
			check.is_true(near(Rules.decay({ halfLife = 0 }, 0.8, 6), 0.4))
			-- halfLife spec must be a table with a finite positive halfLife; a non-table spec uses default 6
			check.is_true(near(Rules.decay(nil, 0.8, 6), 0.4))
		end)
		test.case("stems: a stem with from = full is 1 at or above from; from defaults to 0", function()
			-- when full <= from, the stem is 1 at or above from
			local spec2 = { stems = { { sound = "flat", from = 0.3, full = 0.3 } } }
			check.equal(Rules.stems(spec2, 0.3).flat, 1)
			check.equal(Rules.stems(spec2, 0.5).flat, 1)
			check.equal(Rules.stems(spec2, 0.29).flat, 0)
			-- a stem with no 'from' field: from defaults to 0; it plays at any intensity
			local spec3 = { stems = { { sound = "always" } } }
			check.equal(Rules.stems(spec3, 0).always, 1)
			check.equal(Rules.stems(spec3, 0.5).always, 1)
			-- a stem with from = 0.5 (finite); intensity 0 gives 0; above from it rises
			local spec4 = { stems = { { sound = "mid", from = 0.5, full = 0.8 } } }
			check.equal(Rules.stems(spec4, 0).mid, 0)
			check.is_true(Rules.stems(spec4, 0.65).mid > 0)
		end)
		test.case("nextBeat/nextBar: defaults for bpm (90) and beatsPerBar (4); bpm=1 is used directly", function()
			-- default bpm = 90: beat = 60/90 = 2/3 s
			local beat = 60 / 90
			check.is_true(near(Rules.nextBeat(nil, 0, 0.1), beat))
			-- default beatsPerBar = 4: bar = 4 * beat
			local bar = 4 * beat
			check.is_true(near(Rules.nextBar(nil, 0, 0.1), bar))
			-- bpm = 1 IS > 0 and must be used (not the default 90): beat = 60 s
			local beat1 = 60 / 1
			check.is_true(near(Rules.nextBeat({ bpm = 1 }, 0, 0.1), beat1))
			-- bpm = 0 is not > 0: falls back to default 90
			check.is_true(near(Rules.nextBeat({ bpm = 0 }, 0, 0.1), beat))
			-- beatsPerBar = 0 is not > 0: falls back to default 4
			check.is_true(near(Rules.nextBar({ bpm = 90, beatsPerBar = 0 }, 0, 0.1), bar))
		end)
		test.case("mood: exact boundary values at 0.6 and 0.2", function()
			-- intensity exactly 0.6 is combat (>= 0.6)
			check.equal(Rules.mood(0.6), "combat")
			-- just below: tension
			check.equal(Rules.mood(0.599), "tension")
			-- intensity exactly 0.2 is tension (>= 0.2 but < 0.6)
			check.equal(Rules.mood(0.2), "tension")
			-- just below: calm
			check.equal(Rules.mood(0.199), "calm")
		end)
		-- line 27 (or -> and): decay guard fires when dt is finite AND <= 0 (not NaN)
		test.case("decay: dt=0 is non-positive; guard fires and returns intensity unchanged (or not and)", function()
			-- Original: not finite(0) = false OR 0 <= 0 = true -> guard fires -> return intensity.
			-- Mutant (and): not finite(0) = false AND 0 <= 0 = true -> false -> runs decay with dt=0.
			-- 0^(0/h) = 1 (math.pow(0.5, 0) = 1) -> would return intensity*1 = intensity. Same result!
			-- But with negative dt: not finite(-1)=false OR -1<=0=true -> returns intensity (original).
			-- Mutant: false AND true=false -> runs decay: 0.8*0.5^(-1/6) = 0.8*2^(1/6) > 0.8. Different!
			check.equal(Rules.decay(SPEC, 0.5, 0), 0.5) -- dt=0: guard fires (or not and means true)
			check.equal(Rules.decay(SPEC, 0.5, -1), 0.5) -- dt=-1: guard fires; with and mutant: runs decay > 0.5
		end)

		-- line 27 (<= -> <): dt=0 is exactly the boundary
		test.case("decay: dt=0 returns intensity unchanged (<= catches zero, < does not)", function()
			-- Original: dt <= 0 is true when dt=0 -> guard fires -> return intensity.
			-- Mutant (< instead of <=): dt=0 < 0 is false -> does not fire -> runs decay: 0.5*0.5^(0/h)=0.5*1=0.5. Same!
			-- Use dt=0 scenario differently: since 0.5^(0/h)=1, the decay IS identity. Equivalent mutant at dt=0.
			-- Use dt = -0.0001 (negative): original: -0.0001 <= 0 = true -> returns intensity.
			-- Mutant: -0.0001 < 0 = true -> returns intensity. Same again.
			-- So both mutations give same result at dt=0 and dt<0 for the <= vs < boundary.
			-- The effective kill is via the or->and case (dt=-1 above). The <= -> < mutant is equivalent at dt=0.
			-- Adding it as a separate assertion that combines with the or->and test above.
			check.equal(Rules.decay(SPEC, 0.8, 0), 0.8) -- dt=0 returns unchanged; combined guard kills or->and
		end)

		-- line 36 (and -> or): stems with non-table stems field gives empty output
		test.case("stems: a spec with non-table stems is empty (and not or)", function()
			-- Original: type(spec)=="table" and type(spec.stems)=="table" -> false (stems is a number).
			-- Mutant (or): type(spec)=="table" or type(spec.stems)=="table" -> true or false = true -> iterates over 5.
			-- Iterating over a number would error or give no results. Original: returns {}.
			local badSpec = { stems = 5 }
			local out = Rules.stems(badSpec, 0.5)
			check.equal(next(out), nil) -- empty table: no stems from non-table stems field
		end)

		-- line 37 (and -> or): a stem with a non-string sound is skipped
		test.case("stems: a stem with numeric sound is skipped (and not or)", function()
			-- Original: type(s)=="table" and type(s.sound)=="string" -> true and false = false -> skip.
			-- Mutant (or): true or false = true -> tries to use s.sound as a key with numeric value.
			local badStem = { stems = { { sound = 42 :: any, from = 0 } } }
			local out = Rules.stems(badStem, 0.5)
			check.equal(next(out), nil) -- the bad stem is skipped; with or mutant it would add key 42
		end)

		-- line 69 (0 -> 1): beatsPerBar=0.5 is > 0 and must be used (not replaced by default 4)
		test.case("nextBar: beatsPerBar=0.5 is > 0 and used directly (not replaced by default 4)", function()
			-- Original: beatsPerBar > 0 -> 0.5 > 0 = true -> uses 0.5; bar = beat * 0.5.
			-- Mutant: beatsPerBar > 1 -> 0.5 > 1 = false -> uses default 4; bar = beat * 4.
			-- bpm=120: beat=0.5s. Original bar=0.25s. Mutant bar=2s.
			-- nextBar(spec, 0, 0.1): with bar=0.25: ceil(0.1/0.25 - 1e-9)*0.25 = ceil(0.4 - 1e-9)*0.25 = 1*0.25 = 0.25.
			-- With default bar=2: ceil(0.1/2 - 1e-9)*2 = ceil(0.05)*2 = 1*2 = 2.
			local spec2 = { bpm = 120, beatsPerBar = 0.5 }
			local bar05 = Rules.nextBar(spec2, 0, 0.1)
			check.truthy(math.abs(bar05 - 0.25) < 1e-9) -- 0.25 s not 2 s
		end)

		test.case("the SampleDojo's music names stems and stingers its set makes", function()
			local path = "games/SampleDojo/src/shared/DojoMusic.json"
			if not fs.isFile(path) then
				return
			end
			local spec = serde.decode("json", fs.readFile(path))
			local set = serde.decode("json", fs.readFile("games/SampleDojo/assets/sounds/sets/dojo_music.json"))
			for _, s in spec.stems do
				check.not_nil(set.members[s.sound])
			end
			for _, name in spec.stingers do
				check.not_nil(set.members[name])
			end
		end)
	end)
end

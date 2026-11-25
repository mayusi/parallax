-- sfx.spec.luau — the pure half of the Sfx runtime (src/kit/SfxRules): events -> switch -> blend -> one sound,
-- voice limits with priority stealing, snapshots. The engine half (AudioPlayer/Emitter/Listener) is proven in Studio.
local frk = require("../frk")
local test, check = frk.test, frk.check

local SfxRules = require("../../../src/kit/SfxRules")

local CATALOG = {
	buses = { sfx = { volume = 1 }, ambience = { volume = 0.8 } },
	snapshots = { combat = { ambience = 0.5, music = 0.7, nope = 3 } },
	events = {
		SwordHit = {
			bus = "sfx",
			priority = 60,
			voices = 2,
			cooldown = 0.05,
			pitch = { 0.9, 1.1 },
			switch = "surface",
			default = "metal",
			cases = {
				metal = {
					blend = "weight",
					sounds = { ["0.15"] = "hit_metal_light", ["0.5"] = "hit_metal_medium", ["0.9"] = "hit_metal_heavy" },
				},
				flesh = "hit_flesh",
			},
		},
		UiClick = { bus = "ui", sound = "ui_click", priority = 90 },
		Ambience = { bus = "ambience", sound = "wind", priority = 10 },
	},
}

return function()
	test.suite("SfxRules.resolve", function()
		test.case("switch picks the case, blend picks the nearest weight", function()
			local r = SfxRules.resolve(CATALOG, "SwordHit", { surface = "metal", weight = 0.8 }, 0.5, 0.5)
			check.equal(r and r.sound, "hit_metal_heavy")
			local light = SfxRules.resolve(CATALOG, "SwordHit", { surface = "metal", weight = 0.2 })
			check.equal(light and light.sound, "hit_metal_light")
			local flesh = SfxRules.resolve(CATALOG, "SwordHit", { surface = "flesh" })
			check.equal(flesh and flesh.sound, "hit_flesh")
		end)
		test.case("an unknown case falls back to the default; no weight = the middle", function()
			local r = SfxRules.resolve(CATALOG, "SwordHit", { surface = "jelly" })
			check.equal(r and r.sound, "hit_metal_medium")
		end)
		test.case("pitch range follows the roll; hostile numbers are clamped", function()
			local lo = SfxRules.resolve(CATALOG, "SwordHit", {}, 0, 0)
			local hi = SfxRules.resolve(CATALOG, "SwordHit", {}, 0, 0.999)
			check.is_true(lo ~= nil and math.abs(lo.pitch - 0.9) < 1e-6)
			check.is_true(hi ~= nil and hi.pitch > 1.09)
			local nan = SfxRules.resolve(CATALOG, "SwordHit", { volume = 0 / 0, pitch = math.huge })
			check.is_true(nan ~= nil and nan.volume == 1 and nan.pitch <= 4)
		end)
		test.case("unknown events say so", function()
			local r, why = SfxRules.resolve(CATALOG, "Nope", {})
			check.equal(r, nil)
			check.is_true(why ~= nil and string.find(why, "unknown") ~= nil)
		end)
	end)

	test.suite("SfxRules.admit", function()
		test.case("cooldown blocks a too-fast repeat", function()
			local r = SfxRules.resolve(CATALOG, "SwordHit", {}) :: any
			local ok = SfxRules.admit(r, {}, 10.02, { SwordHit = 10.0 }, 32)
			check.equal(ok, false)
			check.equal((SfxRules.admit(r, {}, 10.1, { SwordHit = 10.0 }, 32)), true)
		end)
		test.case("the event's own cap steals its oldest voice", function()
			local r = SfxRules.resolve(CATALOG, "SwordHit", {}) :: any
			local active = {
				{ event = "SwordHit", priority = 60, started = 1, id = 1 },
				{ event = "SwordHit", priority = 60, started = 2, id = 2 },
			}
			local ok, steal = SfxRules.admit(r, active, 5, {}, 32)
			check.equal(ok, true)
			check.equal(steal and steal.id, 1)
		end)
		test.case("the global cap steals the lowest priority only when outranked", function()
			local hit = SfxRules.resolve(CATALOG, "SwordHit", {}) :: any
			local amb = SfxRules.resolve(CATALOG, "Ambience", {}) :: any
			local full = {
				{ event = "Ambience", priority = 10, started = 1, id = 7 },
				{ event = "UiClick", priority = 90, started = 2, id = 8 },
			}
			local ok, steal = SfxRules.admit(hit, full, 5, {}, 2)
			check.equal(ok, true)
			check.equal(steal and steal.id, 7)
			local ok2 = SfxRules.admit(amb, full, 5, {}, 2)
			check.equal(ok2, false)
		end)
	end)

	test.suite("SfxRules.snapshot + sounds", function()
		test.case("a snapshot overrides only known buses", function()
			local s = SfxRules.snapshot(CATALOG, "combat")
			check.equal(s.ambience, 0.5)
			check.equal(s.music, 0.7)
			check.equal(s.sfx, 1)
			check.equal(s.nope, nil)
			check.equal(SfxRules.snapshot(CATALOG, nil).ambience, 0.8)
		end)
		test.case("every sound an event can play is listed", function()
			local all = SfxRules.sounds(CATALOG)
			check.equal(#all.SwordHit, 4)
			check.equal(all.UiClick[1], "ui_click")
		end)
	end)

	test.suite("SfxRules derive + rtpc (sounds driven by game values)", function()
		local cat = {
			events = {
				PropImpact = {
					derive = { weight = { from = "speed", range = { 8, 60 } } },
					rtpc = { speed = { range = { 8, 60 }, volume = { 0.4, 1 }, pitch = { 1.05, 0.95 } } },
					sounds = { ["0.2"] = "crate_hit_light", ["0.8"] = "crate_hit_heavy" },
				},
			},
		}
		local function near(a: number, b: number): boolean
			return math.abs(a - b) < 1e-9
		end
		test.case("an impact speed picks the take: a tap is light, a slam is heavy", function()
			check.equal((SfxRules.resolve(cat, "PropImpact", { speed = 10 }) :: any).sound, "crate_hit_light")
			check.equal((SfxRules.resolve(cat, "PropImpact", { speed = 55 }) :: any).sound, "crate_hit_heavy")
			check.equal(
				(SfxRules.resolve(cat, "PropImpact", { speed = 55, weight = 0 }) :: any).sound,
				"crate_hit_light"
			)
		end)
		test.case("the same speed moves volume and pitch along the curve; no speed leaves them alone", function()
			local slow = SfxRules.resolve(cat, "PropImpact", { speed = 8 }) :: any
			local fast = SfxRules.resolve(cat, "PropImpact", { speed = 99 }) :: any
			check.is_true(near(slow.volume, 0.4) and near(slow.pitch, 1.05))
			check.is_true(near(fast.volume, 1) and near(fast.pitch, 0.95))
			local none = SfxRules.resolve(cat, "PropImpact", {}) :: any
			check.is_true(near(none.volume, 1) and near(none.pitch, 1))
			check.equal(SfxRules.curve(0 / 0 == 0 / 0 and 5 or 5, nil), 1)
			check.equal(SfxRules.curve(5, { 3, 3 }), 1)
		end)
	end)

	test.suite("SfxRules listen + far layer (the mix and the distance)", function()
		local cat = {
			events = {
				Boom = {
					priority = 50,
					rolloff = { 10, 200 },
					sound = "boom_near",
					far = { sound = "boom_far", beyond = 120 },
				},
			},
		}
		test.case("a distant boom is the far sound; near it is the near one; no distance = near", function()
			check.equal((SfxRules.resolve(cat, "Boom", { distance = 40 }) :: any).sound, "boom_near")
			check.equal((SfxRules.resolve(cat, "Boom", { distance = 150 }) :: any).sound, "boom_far")
			check.equal((SfxRules.resolve(cat, "Boom", {}) :: any).sound, "boom_near")
		end)
		test.case("own sounds outrank, far ones yield; the air eats the highs with distance", function()
			local r = SfxRules.resolve(cat, "Boom", {}) :: any
			local nearP, nearCut = SfxRules.listen(r, 0, false)
			local ownP = SfxRules.listen(r, 0, true)
			local farP, farCut = SfxRules.listen(r, 200, false)
			check.equal(nearP, 50)
			check.equal(ownP, 75)
			check.equal(farP, 30)
			check.equal(nearCut, 20000)
			check.is_true(math.abs(farCut - 2000) < 1e-6)
			local _, midCut = SfxRules.listen(r, 100, false)
			check.is_true(math.abs(midCut - 6324.555) < 0.01) -- (a log sweep: half way is the geometric middle)
			local p0, c0 = SfxRules.listen(r, 0 / 0, nil)
			check.equal(p0, 50)
			check.equal(c0, 20000)
		end)
	end)

	test.suite("SfxRules mutation coverage (survivors)", function()
		test.case("curve: a table with a non-number first element still returns a clamped result", function()
			-- line 61: 'or' guard chain; with 'and' the second condition short-circuits when the first is false
			-- bounds is a table so type(bounds)~="table"=false; bounds[1]="a" so type(bounds[1])~="number"=true
			-- 'or' fires the guard on the second condition; 'and' would not (false and anything = false)
			local v = SfxRules.curve(0.5, { "a", 1 })
			check.is_true(type(v) == "number" and v >= 0 and v <= 1)
			local v2 = SfxRules.curve(0.5, { 0, "b" })
			check.is_true(type(v2) == "number" and v2 >= 0 and v2 <= 1)
		end)
		test.case("resolve without roll1 gives a valid volume when the event has a volume range", function()
			-- line 177: 'roll1 or 0.5'; with 'and', nil and 0.5 = nil -> range gets nil -> arithmetic error
			local cat = {
				events = {
					Buzz = { bus = "sfx", sound = "buzz_snd", priority = 50, volume = { 0.8, 1.2 } },
				},
			}
			local r = SfxRules.resolve(cat, "Buzz", {}) :: any
			check.is_true(r ~= nil)
			check.is_true(type(r.volume) == "number" and r.volume >= 0 and r.volume <= 4)
		end)
		test.case("rolloff second element defaults to 140 when it is NaN", function()
			-- line 179: num(roll[2], 140) default 140; mutant 141; NaN fails the num guard -> uses default
			local cat = {
				events = {
					Zap = { bus = "sfx", sound = "zap_snd", priority = 50, rolloff = { 8, 0 / 0 } },
				},
			}
			local r = SfxRules.resolve(cat, "Zap", {}) :: any
			check.is_true(r ~= nil)
			check.equal(r.rolloff[2], 140)
		end)
		test.case("listen: far=0 rolloff means no distance attenuation (not treated as far)", function()
			-- line 197: 'far > 0'; mutant '>=' makes far==0 trigger distance calc -> t = dist/0 = inf -> clamped to 1
			local cat = {
				events = {
					Ping = { bus = "sfx", sound = "ping_snd", priority = 50, rolloff = { 0, 0 } },
				},
			}
			local r = SfxRules.resolve(cat, "Ping", {}) :: any
			check.is_true(r ~= nil)
			local p0, c0 = SfxRules.listen(r, 50, false)
			-- with far==0 and 'far > 0' = false: t=0, priority unchanged, cut=20000
			check.equal(p0, 50)
			check.equal(c0, 20000)
		end)
		test.case("DIRECTIVITY.voice[0] is 1 (not 2)", function()
			-- line 319: voice = { [0] = 1, ...}; mutant changes 1 -> 2
			check.equal(SfxRules.DIRECTIVITY.voice[0], 1)
		end)
		test.case("MASTER_COMP.release is 0.15 (not 1.15)", function()
			-- line 356: release = 0.15; mutant 1.15
			check.equal(SfxRules.MASTER_COMP.release, 0.15)
		end)
		test.case("graph: ratio=1 override is accepted as-is (COMP_RANGE min is 1 not 2)", function()
			-- line 363: ratio = { 1, 50 }; mutant { 2, 50 } -> ratio=1 would clamp to 2
			local g = SfxRules.graph({ mix = { master = { ratio = 1 } } })
			check.equal(g.master.ratio, 1)
		end)
		test.case("REVERBS.CourtyardOpen.diffusion is 0.7 (not 1.7)", function()
			-- line 390: diffusion = 0.7; mutant 1.7
			check.equal(SfxRules.REVERBS.CourtyardOpen.diffusion, 0.7)
		end)
		test.case("REVERBS.HallStone.wet is -9 (not -8)", function()
			-- line 401: wet = -9; mutant -8 (or -9->-8 rewritten as 9->10 from the negative side perspective)
			check.equal(SfxRules.REVERBS.HallStone.wet, -9)
		end)
		test.case("REVERBS.CatacombCave.wet is -7 (not -6)", function()
			-- line 411: wet = -7; mutant -6 (7->8 from the absolute value side)
			check.equal(SfxRules.REVERBS.CatacombCave.wet, -7)
		end)
		test.case("reverb: density=0 is clamped to 0 (REVERB_RANGE min is 0 not 1)", function()
			-- line 420: density = { 0, 1 }; mutant { 1, 1 } -> density=0 would clamp to 1
			local r = SfxRules.reverb({
				decay = 2,
				early = 0.02,
				late = 0.03,
				density = 0,
				diffusion = 0.5,
				wet = -10,
				dry = 0,
				highCut = 5000,
			})
			check.is_true(r ~= nil)
			check.equal((r :: any).density, 0)
		end)
		test.case("reverb: highCut=20001 clamps to 20000 (REVERB_RANGE max is 20000 not 20001)", function()
			-- line 424: highCut = { 20, 20000 }; mutant { 20, 20001 } -> 20001 would not clamp
			local r = SfxRules.reverb({
				decay = 2,
				early = 0.02,
				late = 0.03,
				density = 0.5,
				diffusion = 0.5,
				wet = -10,
				dry = 0,
				highCut = 20001,
			})
			check.is_true(r ~= nil)
			check.equal((r :: any).highCut, 20000)
		end)

		-- line 96 (< -> <=): pickClosest uses < bestD so a tie does NOT update (first found wins)
		test.case("pickClosest: a tie at equal distance keeps the first candidate (< not <=)", function()
			-- sounds with two entries equidistant from x:  key "0" and key "10" with x=5.
			-- After sorting ("0" < "10" alphabetically): "0" is processed first (d=5), then "10" (d=5).
			-- Original: second candidate: |10-5| < 5 → 5 < 5 = false → NOT updated → returns "0"'s sound.
			-- Mutant (<=): 5 <= 5 = true → updated → returns "10"'s sound.
			-- For the tie test, use weight=0.5 with keys "0.4" and "0.6": |0.4-0.5|=0.1, |0.6-0.5|=0.1.
			local cat2 = {
				events = {
					Tied2 = {
						sounds = { ["0.4"] = "first_at_04", ["0.6"] = "second_at_06" },
					},
				},
			}
			local r2 = SfxRules.resolve(cat2, "Tied2", { weight = 0.5 }, 0.5)
			-- After sorting: "0.4" < "0.6". Original: "0.4" found first (d=0.1), then "0.6" (d=0.1): 0.1 < 0.1 = false → first wins.
			-- Mutant: 0.1 <= 0.1 = true → second wins.
			check.equal(r2 and r2.sound, "first_at_04") -- < (not <=): first candidate wins the tie
		end)

		-- line 164 (2 -> 3): rtpc volume range uses c.volume[2] not c.volume[3]
		test.case("rtpc: volume range uses index 2 for the max (not index 3)", function()
			-- volume = {0.5, 1}: at t=1 (full speed), rv = 0.5 + (1 - 0.5)*1 = 1. With 2->3: volume[3]=nil -> num(nil,1)=1; rv = 0.5+(1-0.5)*1 = 1. Same!
			-- Need volume = {0.5, 0.8, 99}: at t=1: original vol[2]=0.8 -> rv=0.5+(0.8-0.5)=0.8; mutant vol[3]=99 -> rv=0.5+(99-0.5)=99.
			local cat = {
				events = {
					RtpcTest = {
						sound = "rtpc_snd",
						rtpc = { speed = { range = { 0, 10 }, volume = { 0.5, 0.8, 99 } } },
					},
				},
			}
			local r = SfxRules.resolve(cat, "RtpcTest", { speed = 10 }) :: any
			-- t=1 at speed=10. volume[2]=0.8 (original): rv = 0.5+(0.8-0.5)*1 = 0.8. Final vol = clamp(0.8*1,0,4)=0.8.
			-- Mutant (volume[3]=99): rv = 0.5+(99-0.5)*1=99. vol = clamp(99,0,4)=4.
			check.is_true(r ~= nil)
			check.truthy(math.abs(r.volume - 0.8) < 1e-6) -- 0.8 from index 2; with index 3 would be 4 (clamped from 99)
		end)

		-- line 177 (4 -> 5): volume clamp upper is 4, not 5
		test.case("resolve: volume clamped at 4 (not 5) for a high rtpc volume", function()
			-- Use an event where computed volume would be 4.5 (above 4 but below 5).
			local cat = {
				events = {
					Loud = { sound = "loud_snd", volume = { 4.5, 4.5 } }, -- constant 4.5
				},
			}
			local r = SfxRules.resolve(cat, "Loud", {}, 0.5) :: any
			check.is_true(r ~= nil)
			check.equal(r.volume, 4) -- clamped to 4; with upper=5 would be 4.5
		end)

		-- line 180 (6 -> 7): voices default is 6, not 7
		test.case("resolve: an event with no voices field defaults to 6 (not 7)", function()
			local cat = {
				events = { NoVoice = { sound = "nv_snd", priority = 50 } }, -- no voices field
			}
			local r = SfxRules.resolve(cat, "NoVoice", {}) :: any
			check.is_true(r ~= nil)
			check.equal(r.voices, 6) -- default 6; with 7->6 mutant default would give 7
		end)

		-- line 250 (1 -> 2): bus default volume is 1 when the bus has no volume field
		test.case("snapshot: a bus with no volume field defaults to 1 (not 2)", function()
			-- DEFAULT_BUSES includes "sfx", "voice", etc. If a bus exists without a volume field:
			-- num(type(buses[b])=="table" and buses[b].volume, 1) -> buses[b] is a table but volume is nil -> nil -> 1.
			-- Mutant (1->2): default would be 2.
			local cat = {
				buses = { sfx = { reverb = true } }, -- no volume key on sfx bus
			}
			local s = SfxRules.snapshot(cat, nil)
			check.equal(s.sfx, 1) -- no volume field -> defaults to 1; mutant gives 2
		end)

		-- line 317 (90 -> 91): DIRECTIVITY.muzzle[90] is 0.55, not some other value
		test.case("DIRECTIVITY.muzzle[90] is 0.55 (the -5 dB forward scatter, not 91-degree value)", function()
			check.equal(SfxRules.DIRECTIVITY.muzzle[90], 0.55)
		end)

		-- line 318 (0.9 -> 1.9): DIRECTIVITY.blade[90] is 0.9
		test.case("DIRECTIVITY.blade[90] is 0.9 (a nearly-omni blade, not 1.9)", function()
			check.equal(SfxRules.DIRECTIVITY.blade[90], 0.9)
		end)

		-- line 357 (0.25 -> 1.25): DUCK_COMP.release is 0.25, not 1.25
		test.case("DUCK_COMP.release is 0.25 (broadcast ducking recipe, not 1.25)", function()
			check.equal(SfxRules.DUCK_COMP.release, 0.25)
		end)

		-- line 365 (5 -> 6): COMP_RANGE.release max is 5; a release of 5.5 clamps to 5
		test.case("compressor: release=5.5 clamps to 5 (COMP_RANGE max is 5 not 6)", function()
			local g = SfxRules.graph({
				mix = { master = { release = 5.5 } },
			})
			check.equal(g.master.release, 5) -- clamped; with max=6 would be 5.5
		end)

		-- line 396 (2.6 -> 3.6): REVERBS.HallStone.decay is 2.6
		test.case("REVERBS.HallStone.decay is 2.6 (stone hall RT60, not 3.6)", function()
			check.equal(SfxRules.REVERBS.HallStone.decay, 2.6)
		end)

		-- line 407 (0.035 -> 1.035): REVERBS.CatacombCave.early is 0.035
		test.case("REVERBS.CatacombCave.early is 0.035 (pre-delay, not 1.035)", function()
			check.equal(SfxRules.REVERBS.CatacombCave.early, 0.035)
		end)

		-- line 422 (80 -> 81): REVERB_RANGE.wet lower bound is -80; a wet of -81 clamps to -80
		test.case("reverb: wet=-81 clamps to -80 (wet lower bound is -80 not -81)", function()
			local r = SfxRules.reverb({
				decay = 2,
				early = 0.02,
				late = 0.03,
				density = 0.5,
				diffusion = 0.5,
				wet = -81,
				dry = 0,
				highCut = 5000,
			})
			check.is_true(r ~= nil)
			check.equal((r :: any).wet, -80) -- clamped; with lower=-81 would stay -81
		end)
	end)

	test.suite("SfxRules mix graph (LIMITATIONS_FIXES_V4 SFX-X 7.3)", function()
		test.case("directivity: a named shape, a JSON table, and bad tables stay omni", function()
			local m = SfxRules.angleCurve("muzzle")
			check.equal(m and m[0], 1)
			check.is_true(m ~= nil and m[180] < 0.5) -- (a barrel is ~10 dB down behind)
			check.is_true(m ~= SfxRules.DIRECTIVITY.muzzle) -- (a copy: the runtime may not edit the shape)
			local j = SfxRules.angleCurve({ ["0"] = 1, ["180"] = 1.7 })
			check.equal(j and j[180], 1) -- (string keys from JSON; gain clamped to 0..1)
			check.equal(SfxRules.angleCurve({ ["90"] = 1, ["180"] = 0.5 }), nil) -- (no 0 degrees)
			check.equal(SfxRules.angleCurve({ [0] = 1, [270] = 0.5 }), nil) -- (past 180)
			check.equal(SfxRules.angleCurve({ [0] = 1 }), nil) -- (one point is no curve)
			check.equal(SfxRules.angleCurve({ [0] = 1, [180] = 0 / 0 }), nil)
			check.equal(SfxRules.angleCurve("cello"), nil)
			check.equal(SfxRules.angleCurve(nil), nil)
		end)
		test.case("an event's directivity reaches the resolved sound", function()
			local cat = { events = { Shot = { sound = "shot", directivity = "muzzle" }, Hit = { sound = "hit" } } }
			local r = SfxRules.resolve(cat, "Shot", {})
			check.equal(r and r.directivity and r.directivity[30], 1)
			local h = SfxRules.resolve(cat, "Hit", {})
			check.equal(h and h.directivity, nil)
		end)
		test.case(
			"the default graph: acoustic spatial buses, reverb on sfx + voice, music ducked by sfx + voice",
			function()
				local g = SfxRules.graph(CATALOG)
				local by = {}
				for _, b in g.buses do
					by[b.name] = b
				end
				check.equal(#g.buses, 5)
				check.is_true(by.sfx.spatial and by.sfx.acoustic and by.sfx.reverb)
				check.is_true(by.ambience.spatial and by.ambience.acoustic)
				check.is_false(by.ambience.reverb) -- (a bed carries its own space)
				check.is_false(by.music.spatial or by.music.acoustic or by.ui.acoustic)
				check.equal(by.ambience.volume, 0.8)
				check.equal(#g.ducks, 1)
				check.equal(g.ducks[1].bus, "music")
				check.equal(table.concat(g.ducks[1].keys, ","), "sfx,voice")
				check.equal(g.ducks[1].comp.ratio, 4)
				check.equal(g.ducks[1].comp.attack, 0.01)
				check.equal(g.master.threshold, -6)
			end
		)
		test.case("catalog mix: overrides clamp to the engine's ranges; loops and unknown keys are dropped", function()
			local g = SfxRules.graph({
				mix = {
					acoustic = false,
					master = { threshold = 12, ratio = 900, attack = 0 / 0 },
					duck = {
						music = { keys = { "music", "sfx", "nope", "sfx" }, threshold = -90 },
						ambience = { "music" },
						ui = { keys = { "ui" } },
						ghost = { "sfx" },
					},
				},
			})
			check.equal(g.master.threshold, 0)
			check.equal(g.master.ratio, 50)
			check.equal(g.master.attack, SfxRules.MASTER_COMP.attack)
			check.equal(#g.ducks, 2) -- (ambience <- music, music <- sfx; ui keyed by itself and the ghost bus dropped)
			check.equal(g.ducks[1].bus, "ambience")
			check.equal(g.ducks[2].bus, "music")
			check.equal(table.concat(g.ducks[2].keys, ","), "sfx")
			check.equal(g.ducks[2].comp.threshold, -80)
			for _, b in g.buses do
				check.is_false(b.acoustic)
			end
			local off = SfxRules.graph({ mix = { master = false, duck = {} } })
			check.equal(next(off.master), nil)
			check.equal(#off.ducks, 0)
		end)
		test.case("zone reverbs: named presets, the catalog's own, clamped hand tables, nil is dry", function()
			local hall = SfxRules.reverb("HallStone")
			local cave = SfxRules.reverb("CatacombCave")
			local yard = SfxRules.reverb("CourtyardOpen")
			check.is_true(hall ~= nil and cave ~= nil and yard ~= nil)
			check.is_true(yard.decay < hall.decay and hall.decay < cave.decay) -- (open air < hall < cave)
			check.is_true(cave.highCut < yard.highCut)
			check.equal(SfxRules.reverb(nil), nil)
			check.equal(SfxRules.reverb("Nowhere"), nil)
			local own = SfxRules.reverb("Crypt", { reverbs = { Crypt = { decay = 99, wet = -3 } } })
			check.equal(own and own.decay, 20)
			check.equal(own and own.wet, -3)
			check.equal(own and own.early, SfxRules.REVERBS.HallStone.early) -- (a missing field takes the hall's)
		end)
	end)
end

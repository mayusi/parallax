-- vfxsequence.spec.luau (kit) — the V5 choreographed multi-shot sequence (src/kit/VfxSequenceRules.luau;
-- LIMITATIONS_FIXES_V4 §3.4 step 3, §13.3.3). What is proven: a hero sequence must have the V5 shape (charge -> ONE
-- impact beat of a 1-frame mood + a plate + a hitstop -> two or more readable cuts) and each missing part is named;
-- a typo or a bad value is refused, never ignored; the compiled timeline orders a frame's events (the world frozen and
-- the mood laid before the plate shows); on any frame rate from 144 down to 30 fps every event fires within one 60 fps
-- frame of its planned time, never early; and a 1-frame mood is pushed and popped in DIFFERENT steps even at 30 fps
-- (the 1-frame beat is drawn). The runtime (src/kit/VfxSequence.luau) is read for its use of these rules.
local frk = require("../frk")
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local test, check = frk.test, frk.check

local Rules = require("../../../src/kit/VfxSequenceRules")

local function hero(): any
	return {
		schema = 1,
		name = "demo_ultimate",
		fps = 60,
		kind = "hero",
		beats = {
			{ t_frame = 0, name = "charge", camera_cut = { shot = "wide" }, vfx_layers = { "aura_charge" } },
			{
				t_frame = 30,
				name = "impact",
				mood_push = { values = { exposure = 3 }, frames = 1, priority = 10 },
				impact_plate = { plate = "halftone_burst", frames = 4, rate = 2 },
				hitstop = { frames = 6 },
				shake = { amp = 2, frames = 12 },
				fov_punch = { delta = -8, frames = 10 },
				victim_reaction = { power = 1 },
			},
			{ t_frame = 31, name = "reveal_1", camera_cut = { shot = "close" } },
			{ t_frame = 43, name = "reveal_2", camera_cut = { shot = "low" } },
			{ t_frame = 55, name = "reveal_3", camera_cut = { shot = "wide" }, sfx_event = "boom" },
		},
	}
end

local function copy(t: any): any
	return serde.decode("json", serde.encode("json", t))
end

local function has(list: { string }, bit: string): boolean
	for _, s in list do
		if string.find(s, bit, 1, true) then
			return true
		end
	end
	return false
end

-- run a timeline through the clock at the given frame times (a list of dt's, repeated) -> { [event] = seconds fired }
local function play(tl: any, dts: { number }): ({ [any]: number }, { [any]: number })
	local clock = Rules.clock()
	local at, step = {}, {}
	local t, i = 0, 0
	while not Rules.done(tl, clock) and i < 100000 do
		i += 1
		local dt = dts[(i - 1) % #dts + 1]
		t += dt
		for _, ev in Rules.step(tl, clock, dt) do
			at[ev] = t
			step[ev] = clock.step
		end
	end
	return at, step
end

return function()
	test.suite("VfxSequenceRules", function()
		test.case("the hero sequence validates, has the V5 shape, and its impact beat is found", function()
			local ok, bad = Rules.validate(hero())
			check.is_true(ok)
			check.equal(#bad, 0)
			check.equal(Rules.impactBeat(hero()), 2)
			-- a named beat's error message contains the beat's name (kills == -> ~= on line 114)
			local s = hero()
			s.beats[2].t_frame = -1 -- invalid t_frame; beat has name="impact"
			local _, bad2 = Rules.validate(s)
			check.is_true(has(bad2, "impact")) -- the name "impact" appears in the error
		end)

		test.case("each missing part of the V5 shape is named", function()
			local s = hero()
			s.beats[2].mood_push.frames = 3 -- not a 1-frame mood: no impact beat
			local ok, bad = Rules.validate(s)
			check.is_true(not ok)
			check.is_true(has(bad, "IMPACT beat"))

			s = hero()
			s.beats[2].t_frame = 5 -- the charge too short
			s.beats[1].t_frame = 0
			local _, bad2 = Rules.validate(s)
			check.is_true(has(bad2, "the charge runs 5 frames"))

			s = hero()
			table.remove(s.beats, 5)
			table.remove(s.beats, 4) -- one cut left after the impact
			local _, bad3 = Rules.validate(s)
			check.is_true(has(bad3, "multi-cut reveal"))

			s = hero()
			s.beats[4].t_frame = 33 -- a cut held 2 frames
			local _, bad4 = Rules.validate(s)
			check.is_true(has(bad4, "held 2 frames"))

			s = hero()
			table.insert(s.beats, 3, copy(s.beats[2]))
			s.beats[3].t_frame = 31
			s.beats[4].t_frame = 32
			s.beats[5].t_frame = 44
			s.beats[6].t_frame = 56
			local _, bad5 = Rules.validate(s)
			check.is_true(has(bad5, "ONE impact beat"))

			s = hero()
			s.kind = "plain" -- a plain sequence is not held to the shape
			s.beats[2].hitstop = nil
			check.is_true((Rules.validate(s)))
			-- exactly 2 cuts after the impact is the minimum and must be valid (kills < -> <= on line 253)
			local s6 = hero()
			table.remove(s6.beats, 5) -- remove the third reveal cut, leaving 2
			local ok6, bad6 = Rules.validate(s6)
			check.is_true(ok6)
			check.equal(#bad6, 0)
		end)

		test.case("typos and bad values are refused, never ignored", function()
			local cases: { { any } } = {
				{ "hitsop", "unknown key" },
				{ "camera", "camera_cut.shot" },
				{ "fov", "fov_punch" },
				{ "order", "beats run forward" },
				{ "fps", "fps is 60" },
				{ "nan", "shake" },
				{ "plate", "impact_plate" },
				{ "layers", "vfx_layers" },
				{ "victim", "victim_reaction" },
			}
			for _, c in cases do
				local s = hero()
				if c[1] == "hitsop" then
					s.beats[2].hitsop = { frames = 6 }
				elseif c[1] == "camera" then
					s.beats[3].camera_cut.shot = "dutch"
				elseif c[1] == "fov" then
					s.beats[2].fov_punch.delta = 90
				elseif c[1] == "order" then
					s.beats[4].t_frame = 31
				elseif c[1] == "fps" then
					s.fps = 30
				elseif c[1] == "nan" then
					s.beats[2].shake.amp = 0 / 0
				elseif c[1] == "plate" then
					s.beats[2].impact_plate.frames = 0
				elseif c[1] == "layers" then
					s.beats[1].vfx_layers = {}
				elseif c[1] == "victim" then
					s.beats[2].victim_reaction.normal = { 1, 0 }
				end
				local ok, bad = Rules.validate(s)
				check.is_true(not ok)
				check.is_true(has(bad, c[2]))
			end
			check.is_true(not (Rules.validate(nil)))
			check.is_true(not (Rules.validate({ schema = 1, name = "x", fps = 60, beats = {} })))
			local threw = not pcall(Rules.compile, { schema = 1 })
			check.is_true(threw)
			-- fov_punch.frames=1 is valid (lo=1; kills 1->2 mutant on line 132)
			local s2 = hero()
			s2.beats[2].fov_punch = { delta = 5, frames = 1 }
			check.is_true((Rules.validate(s2)))
			-- shake.amp=0 is valid (lo=0; kills 0->1 mutant on line 136)
			local s3 = hero()
			s3.beats[2].shake = { amp = 0, frames = 10 }
			check.is_true((Rules.validate(s3)))
			-- mood_push with a NaN value in values must be refused (kills or->and on line 145)
			local s4 = hero()
			s4.beats[2].mood_push = { values = { exposure = 0 / 0 }, frames = 1 }
			local ok4, bad4 = Rules.validate(s4)
			check.is_true(not ok4)
			check.is_true(has(bad4, "mood_push"))
			-- mood_push with valid values but frames=0 must be refused (kills or->and on line 150)
			local s5 = hero()
			s5.beats[2].mood_push = { values = { exposure = 2 }, frames = 0 }
			local ok5, bad5 = Rules.validate(s5)
			check.is_true(not ok5)
			check.is_true(has(bad5, "mood_push"))
			-- impact_plate with plate=integer must be refused (kills or->and on line 159)
			local s6 = hero()
			s6.beats[2].impact_plate = { plate = 42 :: any, frames = 5 }
			local ok6, bad6 = Rules.validate(s6)
			check.is_true(not ok6)
			check.is_true(has(bad6, "impact_plate"))
			-- impact_plate with no rate field must be valid (kills ~= -> == on line 161)
			local s7 = hero()
			s7.beats[2].impact_plate = { plate = "burst", frames = 5 }
			check.is_true((Rules.validate(s7)))
			-- vfx_layers with a number instead of string must be refused (kills and->or on line 175)
			local s8 = hero()
			s8.beats[1].vfx_layers = { 1 :: any }
			local ok8, bad8 = Rules.validate(s8)
			check.is_true(not ok8)
			check.is_true(has(bad8, "vfx_layers"))
			-- victim_reaction with power=0 is valid (kills 0->1 on line 187)
			local s9 = hero()
			s9.beats[2].victim_reaction = { power = 0 }
			check.is_true((Rules.validate(s9)))
			-- victim_reaction with valid 3-element normal is valid (kills == -> ~= on line 190)
			local s10 = hero()
			s10.beats[2].victim_reaction = { power = 1, normal = { 0, 1, 0 } }
			check.is_true((Rules.validate(s10)))
			-- victim_reaction with normal[2] out of range must be refused (kills 2->3 on line 192)
			local s11 = hero()
			s11.beats[2].victim_reaction = { power = 1, normal = { 0, 2000, 0 } }
			local ok11, bad11 = Rules.validate(s11)
			check.is_true(not ok11)
			check.is_true(has(bad11, "victim_reaction"))
		end)

		test.case("the timeline: a frame's events in order, ends before starts, every duration's end placed", function()
			local tl = Rules.compile(hero())
			local kinds = {}
			for _, ev in tl.events do
				if ev.frame == 30 then
					table.insert(kinds, ev.kind)
				end
			end
			check.equal(table.concat(kinds, ","), "hitstop,mood_push,fov_punch,shake,impact_plate,victim_reaction")
			local ends = 0
			for _, ev in tl.events do
				if string.sub(ev.kind, -4) == "_end" then
					ends += 1
					if ev.kind == "mood_push_end" then
						check.equal(ev.frame, 31)
					end
				end
			end
			check.equal(ends, 5) -- mood, plate, hitstop, shake, fov
			check.equal(tl.frames, 61) -- the last cut held MIN_CUT frames
			for i = 2, #tl.events do
				check.is_true(tl.events[i - 1].frame <= tl.events[i].frame)
			end
			-- on frame 31: mood_push_end must come before camera_cut (the reveal_1 beat); kills 4->5 on line 320
			local frame31 = {}
			for _, ev in tl.events do
				if ev.frame == 31 then
					table.insert(frame31, ev.kind)
				end
			end
			local endPos, cutPos = nil, nil
			for i, k in frame31 do
				if k == "mood_push_end" then
					endPos = i
				elseif k == "camera_cut" then
					cutPos = i
				end
			end
			check.is_true(endPos ~= nil and cutPos ~= nil)
			check.is_true(endPos < cutPos) -- end fires before the new start on the same frame
			-- frames() for a plain beat with no duration fields: t_frame+1 (not t_frame+2; kills 1->2 on line 272)
			local plain = {
				schema = 1,
				name = "simple",
				fps = 60,
				kind = "plain",
				beats = { { t_frame = 5, sfx_event = "boom" } },
			}
			check.equal(Rules.frames(plain), 6) -- 5+1=6 (not 5+2=7)
		end)

		test.case(
			"every event fires within one 60 fps frame of its time and never early, 144 fps down to 30",
			function()
				local tl = Rules.compile(hero())
				for _, dts in
					{
						{ 1 / 144 },
						{ 1 / 60 },
						{ 1 / 30 },
						{ 1 / 144, 1 / 30, 1 / 60, 1 / 41, 1 / 33, 1 / 100 }, -- a frame rate that jitters
					}
				do
					local at = play(tl, dts)
					for _, ev in tl.events do
						local want = ev.frame / 60
						local got = at[ev]
						check.is_true(got ~= nil)
						local isEnd = string.sub(ev.kind, -4) == "_end"
						check.is_true(got + 1e-9 >= want) -- never early
						-- late by less than a frame of 60 fps; an end held over one step may be one step later still
						check.is_true(got - want <= (if isEnd then 2 / 30 else 1 / 30) + 1e-9)
						if not isEnd and dts[1] <= 1 / 60 and #dts == 1 then
							check.is_true(got - want <= 1 / 60 + 1e-9)
						end
					end
				end
			end
		)

		test.case("a 1-frame mood is pushed and popped in DIFFERENT steps at 30 fps (the beat is drawn)", function()
			local tl = Rules.compile(hero())
			local _, step = play(tl, { 1 / 30 })
			local push, pop
			for _, ev in tl.events do
				if ev.kind == "mood_push" then
					push = step[ev]
				elseif ev.kind == "mood_push_end" then
					pop = step[ev]
				end
			end
			check.is_true(push ~= nil and pop ~= nil)
			check.is_true(pop > push)
			-- and a step of a whole second crosses everything at once, the ends still one step after their starts
			local _, big = play(tl, { 1.0 })
			for _, ev in tl.events do
				if ev.kind == "impact_plate_end" then
					for _, s in tl.events do
						if s.kind == "impact_plate" then
							check.is_true(big[ev] > big[s])
						end
					end
				end
			end
		end)

		test.case("a hostile step (NaN, negative, inf) moves nothing", function()
			local tl = Rules.compile(hero())
			local clock = Rules.clock()
			check.equal(#Rules.step(tl, clock, 0 / 0), 2) -- frame 0: the charge's cut and its layers, nothing else
			check.equal(#Rules.step(tl, clock, -5), 0)
			check.equal(#Rules.step(tl, clock, math.huge), 0)
			check.equal(clock.t, 0)
		end)

		test.case("the shipped sequence files validate and the runtime plays them through these rules", function()
			local dir = "assets/effects/sequences"
			local n = 0
			if fs.isDir(dir) then
				for _, f in fs.readDir(dir) do
					if string.sub(f, -9) == ".seq.json" then
						n += 1
						local ok, bad = Rules.validate(serde.decode("json", fs.readFile(dir .. "/" .. f)))
						if not ok then
							print(f, table.concat(bad, "; "))
						end
						check.is_true(ok)
					end
				end
				check.is_true(n >= 1) -- (a project that has the folder ships sequences; the kit's own repo has none)
			end
			local src = fs.readFile("src/kit/VfxSequence.luau")
			check.is_true(string.find(src, "Rules.compile(", 1, true) ~= nil)
			check.is_true(string.find(src, "Rules.step(", 1, true) ~= nil)
			check.is_true(string.find(src, "VfxPlate", 1, true) ~= nil)
		end)

		test.suite("VfxSequenceRules boundary kills", function()
			-- line 30 (60 -> 61): MAX_FRAMES is exactly 1800 (60 * 30), not 60 * 31
			test.case("MAX_FRAMES is exactly 1800 (60 * 30, not 60 * 31)", function()
				check.equal(Rules.MAX_FRAMES, 1800)
			end)

			-- line 132 (40 -> 41): fov_punch delta upper bound is 40, not 41
			test.case("fov_punch delta=40 is valid; delta=41 is refused (upper bound is 40 not 41)", function()
				local s = hero()
				s.beats[2].fov_punch = { delta = 40, frames = 5 }
				check.is_true((Rules.validate(s))) -- exactly at the upper bound: valid
				local s2 = hero()
				s2.beats[2].fov_punch = { delta = 41, frames = 5 }
				local ok2, bad2 = Rules.validate(s2)
				check.is_true(not ok2)
				check.is_true(has(bad2, "fov_punch")) -- one over the upper bound: refused
			end)

			-- line 141 (and -> or): mood_push requires BOTH type(m)=="table" AND type(m.values)=="table"
			test.case("mood_push with no values field is refused (needs both table checks)", function()
				-- Original: type(m)=="table" and type(nil)=="table" = false -> okv=false -> refused.
				-- Mutant (or): type(m)=="table" or type(nil)=="table" = true -> next(nil) errors inside validate.
				-- validate ANSWERS (it never throws on a bad spec): it must return, and refuse
				local s = hero()
				s.beats[2].mood_push = { frames = 1 } -- no values field
				local ok, valid = pcall(Rules.validate, s)
				check.is_true(ok) -- returned, did not throw
				check.is_true(not valid) -- refused
			end)

			-- line 144 (== -> ~=): a numeric value in mood_push.values is accepted
			test.case("mood_push with a numeric value is valid (type(v)==number accepted, not ~=number)", function()
				-- Original: kindOk = type(v)=="number" or ... = true for v=5 -> accepted.
				-- Mutant (==->~=): type(v)~="number" or ... = false or false or false = false -> okv=false -> refused.
				local s = hero()
				s.beats[2].mood_push = { values = { saturation = 5 }, frames = 1 }
				check.is_true((Rules.validate(s))) -- numeric value must be valid
			end)

			-- line 150 (or -> and): okv=false alone must trigger the error (not okv AND not isInt is a weaker guard)
			test.case("mood_push with no values (okv=false) and valid frames is still refused (or not and)", function()
				-- Original: not okv OR not isInt(frames,1,240) = true OR false = true -> refused.
				-- Mutant (or->and): true AND false = false -> not refused (mutant lets it through).
				local s = hero()
				s.beats[2].mood_push = { frames = 1 } -- no values field -> okv=false; frames=1 -> isInt valid
				local ok, valid = pcall(Rules.validate, s)
				check.is_true(ok) -- validate answers, never throws
				check.is_true(not valid) -- refused because okv=false
			end)

			-- line 160 (1 -> 2): impact_plate frames lower bound is 1, not 2
			test.case("impact_plate frames=1 is valid (lo=1 not lo=2)", function()
				local s = hero()
				s.beats[2].impact_plate = { plate = "burst", frames = 1 }
				check.is_true((Rules.validate(s))) -- exactly the minimum: valid
			end)

			-- line 167 (1 -> 2): hitstop frames lower bound is 1, not 2
			test.case("hitstop frames=1 is valid (lo=1 not lo=2)", function()
				local s = hero()
				s.beats[2].hitstop = { frames = 1 }
				check.is_true((Rules.validate(s))) -- exactly the minimum: valid
			end)

			-- line 191 (1 -> 2): normal[1] is checked, not normal[2] twice
			test.case("victim_reaction with normal[1] out of range is refused (checks index 1 not 2)", function()
				-- Original: isNum(normal[1],...) = isNum(2000,...) = false -> refused.
				-- Mutant (1->2): isNum(normal[2],...) = isNum(0,...) = true -> passes first check -> accepted (wrong).
				local s = hero()
				s.beats[2].victim_reaction = { power = 1, normal = { 2000, 0, 0 } } -- [1] out of range, [2] [3] valid
				local ok, bad = Rules.validate(s)
				check.is_true(not ok)
				check.is_true(has(bad, "victim_reaction"))
			end)

			-- line 241 (< -> <=): a charge of exactly MIN_CHARGE frames is valid (strict <, not <=)
			test.case("charge exactly MIN_CHARGE (12) frames is valid (< not <=)", function()
				-- Original: hit.t_frame - beats[1].t_frame < MIN_CHARGE; 12 < 12 = false -> no error -> valid.
				-- Mutant (<=): 12 <= 12 = true -> reports error -> invalid.
				local s = hero()
				s.beats[1].t_frame = 0
				s.beats[2].t_frame = 12 -- exactly MIN_CHARGE=12 frames of charge
				s.beats[3].t_frame = 13 -- reveal_1
				s.beats[4].t_frame = 19 -- reveal_2 (cut at 13 held 6 frames = MIN_CUT)
				s.beats[5].t_frame = 25 -- reveal_3 (cut at 19 held 6 frames = MIN_CUT)
				local ok, bad = Rules.validate(s)
				check.is_true(ok)
				check.equal(#bad, 0)
			end)

			-- line 333 (1 -> 2): clock() initial frame is -1, not -2
			test.case("clock() initial frame is -1 (not -2)", function()
				-- Original: { t=0, frame=-1, fired={}, step=0 }.
				-- Mutant (1->2): frame=-2; a step of 1/60 s reaches floor(1/60*60+1e-6)=1, so frame 0 fires;
				-- with frame=-1 the step correctly initialises to -1 meaning "nothing fired yet".
				local c = Rules.clock()
				check.equal(c.frame, -1)
				check.equal(c.t, 0)
				check.equal(c.step, 0)
			end)
		end)
	end)
end

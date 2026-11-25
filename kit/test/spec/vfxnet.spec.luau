-- vfxnet.spec.luau (kit) - the VFX network route's rules (src/kit/VfxNet.luau; the owner's limitations file, F-R03):
-- who is sent a broadcast, and what a client does with one that arrives late. And that the route USES them: the
-- server's send, the client's receive and the stage's clock, read from their own CODE (comments taken out first).
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local VfxNet = require("../../../src/kit/VfxNet")

local function near(a: number, b: number, tol: number?): boolean
	return math.abs(a - b) <= (tol or 1e-6)
end

-- a source file's code: every comment taken out, runs of blanks made one (so a call split over lines still reads)
local function code(path: string): string
	local out = {}
	for line in string.gmatch(fs.readFile(path), "[^\n]+") do
		local cut = string.find(line, "--", 1, true)
		table.insert(out, if cut then string.sub(line, 1, cut - 1) else line)
	end
	return (string.gsub(table.concat(out, " "), "%s+", " "))
end

return function()
	test.suite("VfxNet", function()
		test.case("the audience is who stands within the reach of the effect", function()
			check.is_true(VfxNet.within(0, 0, 0, 30, 0, 40, 50)) -- 50 studs away, a reach of 50
			check.is_false(VfxNet.within(0, 0, 0, 30, 0, 40.1, 50))
			check.is_false(VfxNet.within(10, 5, -20, 10, 405, -20, 300)) -- straight up counts too
			check.is_true(VfxNet.within(0, 0, 0, 9000, 0, 0, nil)) -- no reach: everyone
		end)
		test.case("a reach is a number of studs, never a mistake", function()
			check.equal(VfxNet.reach(120), 120)
			check.equal(VfxNet.reach(2), VfxNet.REACH_MIN) -- nobody but the caster would see it
			check.equal(VfxNet.reach(nil), nil)
			check.equal(VfxNet.reach("far"), nil)
			check.equal(VfxNet.reach(-5), nil)
			check.equal(VfxNet.reach(0 / 0), nil)
			check.equal(VfxNet.reach(math.huge), nil)
		end)
		test.case(
			"an event on time plays from its start, a late one starts that far in, one that is over is dropped",
			function()
				local what, age = VfxNet.phase(100, 100.05, 2)
				check.equal(what, "play")
				check.equal(age, 0)
				what, age = VfxNet.phase(100, 100.6, 2)
				check.equal(what, "late")
				check.is_true(near(age, 0.6))
				what = VfxNet.phase(100, 102, 2)
				check.equal(what, "drop")
				what = VfxNet.phase(100, 140, math.huge) -- an effect with no end is never over
				check.equal(what, "late")
				what, age = VfxNet.phase(100, 99.2, 2) -- a clock a little off: from the start
				check.equal(what, "play")
				check.equal(age, 0)
				what = VfxNet.phase(100, 100.6, nil) -- no length known: nothing to start part way into
				check.equal(what, "drop")
			end
		)
		test.case("an event with no stamp, or a client with no clock, plays as it always did", function()
			for _, bad in { nil, "now", 0 / 0, math.huge, {} } :: { any } do
				local what, age = VfxNet.phase(bad, 50, 2)
				check.equal(what, "play")
				check.equal(age, 0)
				what = VfxNet.phase(50, bad, 2)
				check.equal(what, "play")
			end
		end)
		test.case("an effect's REAL length counts its hit-stops and its slow motion", function()
			check.is_true(near(VfxNet.realLength(2, nil, nil), 2, 0.01))
			-- two hit-stops of half a second: half a second longer each
			check.is_true(
				near(VfxNet.realLength(2, { { at = 0.5, hold = 0.5 }, { at = 1.5, hold = 0.5 } }, nil), 3, 0.01)
			)
			check.is_true(near(VfxNet.realLength(2, { { at = 0.5 } }, nil), 2 + VfxNet.HOLD, 0.01)) -- the stage's own hold
			-- the middle second at half speed takes two
			check.is_true(near(VfxNet.realLength(3, nil, { { 1, 0.5 }, { 2, 0.5 } }), 4, 0.02))
			check.equal(VfxNet.realLength(math.huge, nil, nil), math.huge)
			check.equal(VfxNet.realLength(nil, nil, nil), 0)
			check.equal(VfxNet.realLength(0 / 0, nil, nil), 0)
		end)
		test.case("where a late effect's own clock is: a hit-stop holds it, slow motion slows it", function()
			local t, left = VfxNet.clockAt(0.75, 2, nil, nil)
			check.is_true(near(t, 0.75, 0.005) and left == 0)
			local hits = { { at = 1, hold = 0.5 } }
			t, left = VfxNet.clockAt(1.2, 2, hits, nil) -- 0.2 s into the hold: the clock stands at the hit, 0.3 s to go
			check.is_true(near(t, 1, 1e-9))
			check.is_true(near(left, 0.3, 0.005))
			t, left = VfxNet.clockAt(2, 2, hits, nil) -- the hold is over: half a second less far than its lateness
			check.is_true(near(t, 1.5, 0.01) and left == 0)
			t = VfxNet.clockAt(1.5, 3, nil, { { 0, 0.5 }, { 3, 0.5 } }) -- at half speed all through
			check.is_true(near(t, 0.75, 0.01))
			t = VfxNet.clockAt(9, 2, hits, nil) -- never past its end
			check.is_true(near(t, 2, 1e-9))
			t = VfxNet.clockAt(1e9, math.huge, nil, nil) -- and never run forward for ever
			check.is_true(near(t, VfxNet.CATCH_MOST, 0.01))
			for _, bad in { nil, "x", 0 / 0, -1, 0 } :: { any } do
				local t0, l0 = VfxNet.clockAt(bad, 2, hits, nil)
				check.equal(t0, 0)
				check.equal(l0, 0)
			end
			check.equal((VfxNet.clockAt(1, nil, nil, nil)), 0) -- no length: nowhere to go
		end)
		test.case("a late stage reaches its moment in small steps of its own clock", function()
			local steps = VfxNet.catchUp(0.25)
			local sum = 0
			for _, d in steps do
				check.is_true(d > 0 and d <= VfxNet.CATCH_STEP + 1e-12)
				sum += d
			end
			check.is_true(near(sum, 0.25, 1e-9))
			check.equal(#steps, 8) -- seven thirtieths and the rest
			check.equal(#VfxNet.catchUp(0), 0)
			check.equal(#VfxNet.catchUp(nil), 0)
			check.equal(#VfxNet.catchUp(0 / 0), 0)
		end)
	end)

	-- THE AUDIENCE WITHOUT A CALLER, and those who come into reach later (stage 37)
	test.suite("an effect's audience comes from the effect itself", function()
		test.case("an effect's extent: the farthest a layer reaches from its origin", function()
			check.equal(VfxNet.extent(nil), 0)
			check.equal(VfxNet.extent({}), 0)
			check.is_true(near(VfxNet.extent({ { kind = "sprite", point = { 3, 4, 0 } } }), 5))
			check.is_true(near(VfxNet.extent({ { kind = "light", point = { 0, 10, 0 }, range = 60 } }), 70)) -- where it is + how far it shines
			check.is_true(near(
				VfxNet.extent({
					{ kind = "mesh", aim = { 64, 0, 0 }, scale = { { 0, { 1, 1, 1 } }, { 1, { 2, 6, 2 } } } },
				}),
				64 + math.sqrt(44)
			))
			check.is_true(near(VfxNet.extent({ { kind = "decal", size = { { 0, 4 }, { 1, 30 } } } }), 15)) -- a mark's half size, at its largest
			check.is_true(near(VfxNet.extent({ { kind = "sprite", scale = 500 } }), 0)) -- (a sprite's scale is not studs)
			check.is_true(near(VfxNet.extent({ 7, { kind = "sound" }, { kind = "sprite", point = { 0, 2, 0 } } }), 2))
			-- a sound's, a shake's, a screen grade's radius is how far it is HEARD or FELT: not a size (times twelve it
			-- made a sound heard at 2600 studs a reach of 31200: everyone)
			local size, felt = VfxNet.extent({
				{ kind = "sound", radius = 600 },
				{ kind = "shake", point = { 0, 40, 0 }, radius = 260 },
			})
			check.is_true(near(size, 40))
			check.is_true(near(felt, 600))
			local crater = VfxNet.extent({ { kind = "crater", radius = 12 } })
			check.is_true(near(crater, 12)) -- a crater's radius IS its size
		end)
		test.case("who decides, in order: the caller, the preset, the game, the kit's rule", function()
			check.equal(VfxNet.audience(false, 50, 80, 1, 10), nil) -- the caller says everyone
			check.equal(VfxNet.audience("all", 50, 80, 1, 10), nil)
			check.equal(VfxNet.audience(120, 50, 80, 1, 10), 120) -- the caller's reach, as it is
			check.equal(VfxNet.audience(nil, "all", 80, 1, 10), nil) -- the preset says everyone
			check.equal(VfxNet.audience(nil, 50, 80, 3, 10), 150) -- the preset's reach grows with the play's scale
			check.equal(VfxNet.audience(nil, nil, false, 1, 10), nil) -- the game says everyone
			check.equal(VfxNet.audience(nil, nil, 80, 3, 10), 80) -- the game's reach is the game's
			check.equal(VfxNet.audience(nil, nil, nil, 1, 10), 300) -- the rule: never under the floor
			check.equal(VfxNet.audience(nil, nil, nil, 1, 100), 1200) -- twelve times the effect's extent
			check.equal(VfxNet.audience(nil, nil, nil, 2, 100), 2400) -- at this scale
			check.equal(VfxNet.audience(nil, nil, nil, nil, nil), 300) -- nothing known: the floor, never everyone by accident
			check.equal(VfxNet.audience(nil, -5, nil, 1, 10), 300) -- a preset reach that is none falls through
			-- only false or "all" mean everyone: a reach that is no reach (a typo) is as if none was given
			check.equal(VfxNet.audience(0, nil, nil, 1, 10), 300)
			check.equal(VfxNet.audience(-5, nil, nil, 1, 10), 300)
			check.equal(VfxNet.audience(true, nil, nil, 1, 10), 300)
			check.equal(VfxNet.audience("100", 50, nil, 1, 10), 50)
			-- as far as a layer says it is heard, as it is - not times twelve
			check.equal(VfxNet.audience(nil, nil, nil, 1, 10, 2600), 2600)
			check.equal(VfxNet.audience(nil, nil, nil, 2, 10, 2600), 5200)
			check.equal(VfxNet.audience(nil, nil, nil, 1, 400, 600), 4800)
			-- the client plays a scale within 0.1 to 10: the reach is counted with the same
			check.equal(VfxNet.audience(nil, 1000, nil, 0.01, 0), VfxNet.reach(100))
			check.equal(VfxNet.audience(nil, nil, nil, 50, 100), 12000)
		end)
		test.case("with no caller's word, a small effect is NOT sent across a map (it was sent to everyone)", function()
			local reach = VfxNet.audience(nil, nil, nil, 1, VfxNet.extent({ { kind = "sprite", point = { 0, 3, 0 } } }))
			check.equal(reach, 300)
			check.is_true(VfxNet.within(0, 0, 0, 200, 0, 0, reach))
			check.is_false(VfxNet.within(0, 0, 0, 900, 0, 0, reach))
		end)
		local function event(over: number, target: boolean?): any
			return {
				id = 1,
				x = 0,
				y = 0,
				z = 0,
				tx = if target then 1000 else nil,
				ty = 0,
				tz = 0,
				reach = 100,
				over = over,
				to = {},
			}
		end
		test.case(
			"who is sent an event at once: those in reach of it or of its target, and anyone with no character",
			function()
				local live = { event(10, true) }
				local sends = VfxNet.newcomers(
					live,
					0,
					{ a = { 50, 0, 0 }, b = { 500, 0, 0 }, c = { 990, 0, 0 }, d = false },
					true
				)
				local got = {}
				for _, s in sends do
					got[s[1]] = true
				end
				check.is_true(got.a and got.c and got.d)
				check.equal(got.b, nil)
				check.equal(#sends, 3)
			end
		)
		test.case("one who comes into reach while the effect still lasts is sent it then - once", function()
			local live = { event(10) }
			check.equal(#VfxNet.newcomers(live, 0, { a = { 50, 0, 0 }, b = { 500, 0, 0 } }), 1)
			check.equal(#VfxNet.newcomers(live, 1, { a = { 50, 0, 0 }, b = { 400, 0, 0 } }), 0) -- b is still out; a is not sent it twice
			local sends = VfxNet.newcomers(live, 2, { a = { 60, 0, 0 }, b = { 90, 0, 0 } })
			check.equal(#sends, 1)
			check.equal(sends[1][1], "b")
			check.equal(sends[1][2], live[1]) -- the event itself: sent with its FIRST stamp, so the client starts it late
			check.equal(#VfxNet.newcomers(live, 3, { a = { 60, 0, 0 }, b = { 500, 0, 0 } }), 0)
			check.equal(#VfxNet.newcomers(live, 4, { a = { 60, 0, 0 }, b = { 90, 0, 0 } }), 0) -- out and in again: not again
			check.equal(#VfxNet.newcomers(live, 5, { c = { 10, 0, 0 } }), 1) -- someone who joined since, and stands in reach
			-- one with no character yet (just joined) is NOT sent what is already playing all over the map
			check.equal(#VfxNet.newcomers(live, 6, { d = false }, false), 0)
			check.equal(#VfxNet.newcomers(live, 6, { d = false }), 0)
			check.equal(#VfxNet.newcomers(live, 7, { d = { 20, 0, 0 } }, false), 1) -- until they stand in reach
		end)
		test.case("an effect that is over is no longer kept, and no one is sent it", function()
			local live = { event(10), event(30) }
			check.equal(#VfxNet.newcomers(live, 10, { a = { 50, 0, 0 } }), 1) -- only the one that still lasts
			check.equal(#live, 1)
			check.equal(live[1].over, 30)
			check.equal(#VfxNet.newcomers(live, 31, { b = { 50, 0, 0 } }), 0)
			check.equal(#live, 0)
		end)
	end)

	test.suite("an effect's clock moves by the real time, not by the frame it was made in", function()
		test.case("played inside a frame of 1 s, its first step moves only the 0.02 s since it was made", function()
			-- (Heartbeat's dt is the PREVIOUS frame: the stage was made at 10.00, the next step comes at 10.02 with dt 1)
			local d, last = VfxNet.stepBy(1.0, 10.02, 10.00)
			check.is_true(math.abs(d - 0.02) < 1e-9)
			check.equal(last, 10.02)
			-- the frames after it move by their own dt (a normal frame: dt and the real time agree)
			local d2, last2 = VfxNet.stepBy(1 / 60, 10.02 + 1 / 60, last)
			check.is_true(math.abs(d2 - 1 / 60) < 1e-9)
			-- a long frame WHILE it plays: the real time has passed, so the clock keeps up with it (sound and server)
			local d3 = VfxNet.stepBy(0.8, last2 + 0.8, last2)
			check.is_true(math.abs(d3 - 0.8) < 1e-9)
		end)
		test.case("a step never runs backwards or on a dt that is no number", function()
			check.equal((VfxNet.stepBy(0.5, 9.0, 10.0)), 0) -- (a clock read out of order)
			check.equal((VfxNet.stepBy(0 / 0, 11.0, 10.0)), 0)
			check.equal((VfxNet.stepBy(-1, 11.0, 10.0)), 0)
			check.equal((VfxNet.stepBy(nil :: any, 11.0, 10.0)), 0)
		end)
	end)

	test.suite("the VFX network route uses its rules", function()
		local server = code("src/kit/Vfx.luau")
		local client = code("src/kit/client/VfxClient.client.luau")
		local stage = code("src/kit/VfxStage.luau")
		local function has(text: string, needle: string): boolean
			return string.find(text, needle, 1, true) ~= nil
		end
		test.case("the server stamps the event, sends the stamp, and sends to its audience only", function()
			check.is_true(has(server, "local sent = Workspace:GetServerTimeNow()"))
			check.is_true(has(server, "remote:FireAllClients(name, where, scale or 1, target, sent)"))
			check.is_true(has(server, "remote:FireClient(send[1], name, where, scale or 1, target, sent)"))
			check.is_true(has(server, "local reach = VfxNet.audience("))
			check.is_true(has(server, "local extent, felt = VfxNet.extent(preset.layers or preset.elements)")) -- with no caller's word: the effect's own size, old presets too
			check.is_true(has(server, "local first = VfxNet.newcomers({ ev }, sent - 1, places, true)")) -- one rule for now and for later
			check.is_true(
				has(server, "for _, send in VfxNet.newcomers(live, Workspace:GetServerTimeNow(), places, false) do")
			)
			check.is_true(has(server, "local ok, why = pcall(function()")) -- one look that throws does not end the watch
			check.is_true(has(server, "remote:FireClient(send[1], ev.name, ev.where, ev.scale, ev.target, ev.sent)")) -- its FIRST stamp
			check.is_true(has(server, "over = sent + length,")) -- kept for as long as it really lasts
		end)
		test.case(
			"the client reads the stamp, measures it against the effect's REAL length, drops or starts late",
			function()
				check.is_true(has(client, "target: unknown, sent: unknown)"))
				check.is_true(has(client, "VfxNet.phase(sent, Workspace:GetServerTimeNow(), Vfx.realLengthOf(name))"))
				check.is_true(has(client, 'if what == "drop" then return end'))
				check.is_true(
					has(client, 'Vfx.play(name, where :: any, s, nil, t, if what == "late" then late else nil)')
				)
			end
		)
		test.case("a late play reaches the stage, which runs ITS clock to where it should be", function()
			check.is_true(has(server, "target = target, late = late })")) -- Vfx.play hands it to the stage
			check.is_true(has(server, "VfxNet.realLength(preset.duration"))
			check.is_true(has(stage, "VfxNet.clockAt(o.late, self.duration, preset.hitstop, preset.timewarp)"))
			check.is_true(has(stage, "for _, d in VfxNet.catchUp(catchTo) do"))
			check.is_true(has(stage, "elseif catching then dt")) -- its steps are the effect's own time: no slow motion on top
			check.is_true(has(stage, "not catching and self.time < h.at and t >= h.at")) -- a hit-stop passed over does not hold the catch-up
			check.is_true(has(stage, "holdUntil = os.clock() + holdLeft")) -- what is left of a hold it lands in is held
			check.is_true(has(stage, "self.catchTo and (el.at or 0) < self.catchTo - 0.1")) -- a sound already past is not played
		end)
	end)
end

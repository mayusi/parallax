-- animmatch.spec.luau — THE WAY IN of pose and distance matching (the owner's method lists, 2026-11-14): a clip that
-- says "match" gets its tables from the build's own step (AnimCmd.matchTables -> kit/anim/match_tables.py `for`) and
-- the game's entry (src/kit/AnimMatch.enterTime, what Anim.play calls) reads them; a clip that asks for a table it
-- cannot give is refused with the reason; the build and the runtime still carry the calls.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local AnimCmd = require("../../cmd/anim")
local AnimMatch = require("../../../src/kit/AnimMatch")

local FPS, N = 30, 21

-- a turn of `deg` about Y, as a clip frame { qx, qy, qz, qw, px, py, pz }
local function frame(deg: number): { number }
	local h = math.rad(deg) / 2
	return { 0, math.sin(h), 0, math.cos(h), 0, 0, 0 }
end

-- a made-up clip: the torso turns 0 -> 100 degrees, the head 0 -> -40; a Hit at 0.5 s (frame 15)
local function clip(match: any, travel: number?, hitAt: number?): any
	local torso, head, times, root = {}, {}, {}, {}
	for i = 0, N - 1 do
		local u = i / (N - 1)
		table.insert(torso, frame(100 * u))
		table.insert(head, frame(-40 * u))
		table.insert(times, i / FPS)
		table.insert(root, { 0, 0, 0, 1, 0, 0, -(travel or 0) * u })
	end
	return {
		schema = 1,
		name = "SpecMatch",
		rig = "R6",
		fps = FPS,
		loop = false,
		times = times,
		events = { { name = "Hit", t = hitAt or 0.5 } },
		joints = { Torso = { frames = torso }, Head = { frames = head } },
		root = if travel then root else nil,
		match = match,
	}
end

local function poseAt(c: any, i: number): { [string]: { number } }
	local f, g = c.joints.Torso.frames[i + 1], c.joints.Head.frames[i + 1]
	return { Torso = { f[1], f[2], f[3], f[4] }, Head = { g[1], g[2], g[3], g[4] } }
end

return function()
	test.suite("anim match: the build's tables and the game's entry", function()
		test.case("a clip that says match pose is entered at the frame nearest the pose, never past its Hit", function()
			local c = clip({ pose = true })
			local tables, why = AnimCmd.matchTables("SpecMatch", c)
			check.truthy(tables ~= nil and why == nil)
			check.equal(#tables.pose.rows, 15) -- frames 0 .. 14: the Hit is frame 15
			for _, i in { 0, 4, 9, 14 } do
				local at = AnimMatch.enterTime({ match = tables }, poseAt(c, i), nil)
				check.truthy(at ~= nil and math.abs((at :: number) - i / FPS) < 1e-6)
			end
			local late = AnimMatch.enterTime({ match = tables }, poseAt(c, 20), nil) -- a pose after the Hit
			check.truthy(late ~= nil and math.abs((late :: number) - 14 / FPS) < 1e-6)
			check.truthy(AnimMatch.enterTime({ match = tables }, nil, 2.0) == nil) -- no distance table was asked for
		end)
		test.case("a clip that travels and says match distance gives the time for the studs left", function()
			local c = clip({ pose = true, distance = true }, 6) -- 6 studs, even speed, 20 frames
			local tables = AnimCmd.matchTables("SpecMatch", c)
			check.truthy(tables ~= nil and math.abs(tables.distance.remaining[1] - 6) < 1e-3)
			local half = AnimMatch.enterTime({ match = tables }, nil, 3.0)
			check.truthy(half ~= nil and math.abs((half :: number) - 10 / FPS) < 1e-4)
			check.truthy(AnimMatch.enterTime({ match = tables }, nil, 99) == 0)
			local toHit = AnimCmd.matchTables("SpecMatch", clip({ distance = "Hit" }, 6))
			-- (only the frames before the Hit: frames 0 .. 14)
			check.truthy(toHit ~= nil and toHit.distance.to == "Hit" and #toHit.distance.remaining == 15)
			local past = AnimMatch.enterTime({ match = tables }, nil, 0.1) -- nearly at the stop: past the Hit
			check.truthy(past ~= nil and math.abs((past :: number) - 14 / FPS) < 1e-6) -- ... the last frame before it
		end)
		test.case("a clip that asks for a table it cannot give is refused, with the reason", function()
			local t1, why1 = AnimCmd.matchTables("SpecMatch", clip({ distance = true })) -- it does not travel
			check.truthy(t1 == nil and string.find(why1 :: string, "does not travel", 1, true) ~= nil)
			local t2, why2 = AnimCmd.matchTables("SpecMatch", clip({ pose = true }, nil, 1 / FPS)) -- the Hit on frame 1
			check.truthy(
				t2 == nil and string.find(why2 :: string, "fewer than 2 frames it may be entered at", 1, true) ~= nil
			)
			local t3, why3 = AnimCmd.matchTables("SpecMatch", clip({ pose = "yes" }))
			check.truthy(t3 == nil and string.find(why3 :: string, '"pose": true', 1, true) ~= nil)
			local t4, why4 = AnimCmd.matchTables("SpecMatch", clip({ motion = true }))
			check.truthy(t4 == nil and string.find(why4 :: string, '"match" is', 1, true) ~= nil)
			local t5 = AnimCmd.matchTables("SpecMatch", clip({ distance = "Land" }, 6)) -- no such event
			check.truthy(t5 == nil)
		end)
		test.case("a body with none of the table's joints is not matched (no silent frame 0)", function()
			local tables = AnimCmd.matchTables("SpecMatch", clip({ pose = true }))
			local r15 = { UpperTorso = { 0, 0.5, 0, 0.86 }, LowerTorso = { 0, 0, 0, 1 } }
			local at, why = AnimMatch.enterTime({ match = tables }, r15, nil)
			check.truthy(at == nil and why == "no shared joint")
			local _, why2 = AnimMatch.enterTime({ match = tables }, nil, 2.0) -- a distance asked of a clip with no distance table
			check.equal(why2, "no table")
			local _, why3 = AnimMatch.enterTime({}, r15, nil)
			check.equal(why3, "no table")
			check.truthy(AnimMatch.enterTime({ match = tables }, {}, nil) == nil)
			check.truthy(AnimMatch.enterTime({ match = tables }, { Head = { 0, 0, 0, 1 } }, nil) ~= nil) -- one shared joint is a body of this rig
		end)
		test.case("a clip with no tables is played from its start", function()
			check.truthy(AnimMatch.enterTime({}, { Torso = { 0, 0, 0, 1 } }, nil) == nil)
			check.truthy(AnimMatch.enterTime(nil, nil, 3) == nil)
		end)
		test.case("a keyframe spec's ask rides on the clip the compiler makes", function()
			local Anim = require("../../lib/anim")
			local spec = {
				name = "SpecAsk",
				rig = "R6",
				fps = 30,
				match = { pose = true },
				keys = {
					{ t = 0, pose = { Torso = { 0, 0, 0 } } },
					{ t = 0.5, pose = { Torso = { 0, 40, 0 } } },
				},
			}
			local made = Anim.clipFromSpec(spec, {})
			check.truthy(made ~= nil and (made :: any).match ~= nil and (made :: any).match.pose == true)
			spec.match = nil
			local plain = Anim.clipFromSpec(spec, {})
			check.truthy(plain ~= nil and (plain :: any).match == nil)
		end)
		test.case("a table of the wrong shape is no table (the clip is played from its start)", function()
			local bad = { match = { pose = { joints = { "Torso" }, rows = { { 0, 0, 0, 1 } } } } } -- no fps
			check.truthy(AnimMatch.enterTime(bad, { Torso = { 0, 0, 0, 1 } }, nil) == nil)
			check.truthy(AnimMatch.enterTime({ match = { distance = { fps = 30, remaining = {} } } }, nil, 1) == nil)
		end)
		test.case("the build and the runtime still carry the calls", function()
			local build = fs.readFile("kit/cmd/anim.luau")
			check.truthy(string.find(build, "AnimCmd.matchTables(src.name, r6)", 1, true) ~= nil)
			check.truthy(string.find(build, "it asks to be matched", 1, true) ~= nil)
			check.truthy(string.find(build, "metas[src.name].match = tables", 1, true) ~= nil)
			local game = fs.readFile("src/kit/Anim.luau")
			check.truthy(string.find(game, "track.TimePosition = at", 1, true) ~= nil)
			check.truthy(string.find(game, "applyRoot(owner, track, m, o.target, entered)", 1, true) ~= nil)
			check.truthy(string.find(game, "AnimMatch.enterTime(clipMeta, pose, distance)", 1, true) ~= nil)
		end)
	end)

	test.suite("anim match: a motion set through the build's own step", function()
		-- three made-up clips: the torso turning 0 -> 100, 0 -> -100 and nodding (about X)
		local function made(name: string, axis: number, sign: number): any
			local torso, head, times = {}, {}, {}
			for i = 0, 40 do
				local h = math.rad(sign * 100 * i / 40) / 2
				local q = { 0, 0, 0, math.cos(h), 0, 0, 0 }
				q[axis] = math.sin(h)
				table.insert(torso, q)
				table.insert(head, { 0, 0, 0, 1, 0, 0, 0 })
				table.insert(times, i / 60)
			end
			return {
				schema = 1,
				name = name,
				rig = "R6",
				fps = 60,
				loop = false,
				times = times,
				events = {},
				joints = { Torso = { frames = torso }, Head = { frames = head } },
			}
		end
		local idle = made("Idle", 3, 0) -- stands still; it loops (41 frames: an odd count)
		idle.loop = true
		local clips = {
			TurnLeft = made("TurnLeft", 2, 1),
			TurnRight = made("TurnRight", 2, -1),
			Nod = made("Nod", 1, 1),
			Idle = idle,
		}
		local dir = "build/selftest/spec_motion_" .. tostring(math.random(1, 1e9))
		local function setFile(names: { string }, rest: string?): string
			fs.writeDir(dir)
			local p = dir .. "/Turns.motion.json"
			local text = '{"clips": ["' .. table.concat(names, '", "') .. '"]'
			fs.writeFile(p, text .. (if rest then ', "rest": "' .. rest .. '"}' else "}"))
			return p
		end
		local function torsoAt(c: any, i: number): { [string]: { number } }
			local f = c.joints.Torso.frames[i + 1]
			return { Torso = { f[1], f[2], f[3], f[4] }, Head = { 0, 0, 0, 1 } }
		end
		test.case(
			"the set's database is baked from the clips the build made, and the game's step plays from it",
			function()
				local db, why = AnimCmd.motionDb(setFile({ "TurnLeft", "TurnRight", "Nod", "Idle" }, "Idle"), clips)
				check.truthy(db ~= nil and why == nil)
				check.truthy(db.fps == 30 and db.rest == "Idle" and db.clips.Idle.loop == true and #db.joints == 2)
				-- the body follows TurnLeft while TurnLeft plays: no jump
				local name, _, jump = AnimMatch.motionStep(
					db,
					torsoAt(clips.TurnLeft, 13),
					torsoAt(clips.TurnLeft, 14),
					1 / 60,
					{ "TurnLeft", 7 }
				)
				check.truthy(name == "TurnLeft" and jump == false)
				-- the body nods while TurnLeft plays: the set goes to Nod
				local n2, f2, j2 =
					AnimMatch.motionStep(db, torsoAt(clips.Nod, 19), torsoAt(clips.Nod, 20), 1 / 60, { "TurnLeft", 6 })
				check.truthy(n2 == "Nod" and j2 == true and math.abs(f2 - 11) <= 1)
				-- TurnLeft is in its last frames: it plays out, whatever the body does
				local last = db.clips.TurnLeft.frames - 1
				local n3, f3, j3 = AnimMatch.motionStep(
					db,
					torsoAt(clips.Nod, 19),
					torsoAt(clips.Nod, 20),
					1 / 60,
					{ "TurnLeft", last + 0.5 }
				)
				check.truthy(n3 == "TurnLeft" and f3 == last and j3 == false)
				pcall(fs.removeDir, dir)
			end
		)
		test.case("a set the game could not play is refused, with the reason", function()
			local db, why = AnimCmd.motionDb(setFile({ "TurnLeft", "Idle", "Spin" }, "Idle"), clips)
			check.truthy(
				db == nil
					and string.find(why :: string, "names the clip Spin, which this build did not make", 1, true)
						~= nil
			)
			local one, why1 = AnimCmd.motionDb(setFile({ "TurnLeft" }, "TurnLeft"), clips)
			check.truthy(one == nil and string.find(why1 :: string, "2 clips or more", 1, true) ~= nil)
			local none, why2 = AnimCmd.motionDb(setFile({ "TurnLeft", "TurnRight" }), clips) -- nothing to rest in
			check.truthy(none == nil and string.find(why2 :: string, 'names its "rest"', 1, true) ~= nil)
			local hard, why3 = AnimCmd.motionDb(setFile({ "TurnLeft", "TurnRight" }, "TurnLeft"), clips)
			check.truthy(hard == nil and string.find(why3 :: string, "its rest TurnLeft does not loop", 1, true) ~= nil)
			pcall(fs.removeDir, dir)
		end)
		test.case(
			"the generated module is one the game can require, and the build and runtime carry the calls",
			function()
				local text = AnimCmd.jsonModule("a comment", { a = { "x]==]y" } })
				check.truthy(
					string.find(text, "JSONDecode([===[", 1, true) ~= nil
						and string.find(text, "]===])", 1, true) ~= nil
				)
				local build = fs.readFile("kit/cmd/anim.luau")
				check.truthy(string.find(build, "AnimCmd.motionDb(`{setDir}/{f}`, r6Clips)", 1, true) ~= nil)
				check.truthy(string.find(build, "[error] motion set {setName}: {why}", 1, true) ~= nil)
				check.truthy(string.find(build, "r6Clips[src.name] = clips.R6 or clip", 1, true) ~= nil)
				local game = fs.readFile("src/kit/Anim.luau")
				-- (the step also takes where the player wants to go and the clips the game allows now: 2026-11-15, A-R02)
				check.truthy(
					string.find(
						game,
						"AnimMatch.motionStep(db, before, pose, dt, current, want, if o.only then o.only() else nil)",
						1,
						true
					) ~= nil
				)
				check.truthy(
					string.find(
						game,
						"want = AnimMatch.wanted(move.X, move.Z, look.X, look.Z, steerHum.WalkSpeed, o.turnIn)",
						1,
						true
					) ~= nil
				)
				check.truthy(string.find(game, "tracks[name].TimePosition = frame / db.fps", 1, true) ~= nil)
				check.truthy(
					string.find(game, "go(rest) -- (a clip that does not loop has played out)", 1, true) ~= nil
				)
				check.truthy(string.find(game, "if jump and name ~= playing then", 1, true) ~= nil)
			end
		)
	end)
end

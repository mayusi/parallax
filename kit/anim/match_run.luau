-- match_run.luau — `lune run kit/anim/match_run.luau <table.json> <queries.json>`: asks the GAME's own matcher
-- (src/kit/AnimMatch.luau) and prints its answers as one JSON line, so the build side (kit/anim/match_tables.py) can
-- be held to it. queries: a list of
--   { "pose": { joint: [x, y, z, w] } }                       on a pose table      -> a frame
--   { "distance": d }                                         on a distance table  -> a frame (between two)
--   { "pose": [...], "vel": [...], "current": [clip, frame]? } on a motion database -> [clip, frame]
--   { "a": [x, y, z, w], "b": [x, y, z, w], "fps": n }         (any table)          -> a velocity
--   { "want": [vx, vz, turn], "only": { clip: true } }         (with a motion query) steering, allowed clips
--   { "wanted": [mx, mz, lx, lz, speed, turnIn?] }             (any table)          -> [vx, vz, turn]
--   { "blend": { set, meta, move: [x, z], speed } }            (any table)          -> the blend route's top clip
--   { "enter": true, "pose": {...} | "distance": d }          on { "match": the build's tables } -> seconds
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local AnimBlend = require("../../src/kit/AnimBlend")
local AnimMatch = require("../../src/kit/AnimMatch")

local tablePath, queryPath = process.args[1], process.args[2]
if not tablePath or not queryPath or not fs.isFile(tablePath) or not fs.isFile(queryPath) then
	print(serde.encode("json", { status = "fail", summary = "usage: match_run.luau <table.json> <queries.json>" }))
	process.exit(1)
end
local t = serde.decode("json", fs.readFile(tablePath))
local queries = serde.decode("json", fs.readFile(queryPath))
local answers = {}
for i, q in queries do
	if q.step ~= nil then
		-- the game's own loop step (src/kit/Anim.motion calls exactly this)
		local name, frame, jump = AnimMatch.motionStep(t, q.prev, q.pose, q.dt, q.current, q.want, q.only)
		answers[i] = { clip = name, frame = frame, jump = jump }
	elseif q.enter ~= nil then
		-- the game's own entry (src/kit/Anim.play calls this on Meta.<clip>): seconds, or -1 for "no such table"
		answers[i] = AnimMatch.enterTime(t, q.pose, q.distance) or -1
	elseif q.blend ~= nil then
		-- THE BLEND ROUTE's answer to the same ask (src/kit/AnimBlend.weights): the clip it gives the most weight
		local Vector3 = (require("@lune/roblox") :: any).Vector3
		local plays = AnimBlend.weights(
			q.blend.set,
			q.blend.meta,
			Vector3.new(q.blend.move[1], 0, q.blend.move[2]),
			q.blend.speed
		)
		local top, most = "", -1
		for name, play in plays do
			if play.weight > most then
				top, most = name, play.weight
			end
		end
		answers[i] = top
	elseif q.wanted ~= nil then
		-- where the player wants to go, in the body's own frame: [mx, mz, lx, lz, speed, turnIn?]
		answers[i] = AnimMatch.wanted(q.wanted[1], q.wanted[2], q.wanted[3], q.wanted[4], q.wanted[5], q.wanted[6])
	elseif q.a then
		answers[i] = AnimMatch.velocity(q.a, q.b, q.fps)
	elseif t.kind == "pose" then
		answers[i] = AnimMatch.poseFrame(t, q.pose)
	elseif t.kind == "distance" then
		answers[i] = AnimMatch.distanceFrame(t, q.distance)
	else
		answers[i] = AnimMatch.motionNext(t, q.pose, q.vel, q.current, q.want, q.only)
	end
end
print(serde.encode("json", { status = "pass", answers = answers }))

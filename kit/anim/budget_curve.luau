-- budget_curve.luau — what the kit's own curve rule (src/kit/AnimCurve thin / lost) would do to built clips, without
-- Studio: for kit/anim/budget.py.
--   lune run kit/anim/budget_curve.luau <out.json> <clip.json> [<clip.json> ...]
-- Per clip: its tracks' keys (a turn and a place count once each a frame; the joints AND the weapon's Handle
-- joint - `grip` / `grip_left` - which the exporter writes and thins too), the keys a curve within the kit's
-- tolerances (AnimCurve.ROT_TOL degrees, AnimCurve.POS_TOL studs) keeps, the most the engine's 30-a-second curve
-- playback would lose (degrees, studs), what a curve animation would be off by AT AN EVENT's own frame (the
-- thinning AND the engine's 30-a-second grid together: a Hit on an odd frame of a 60-a-second clip is not played),
-- and the clip's POPS: a joint that turns more than 90 degrees in one frame is a broken frame, not motion - its
-- loss is counted apart.
local AnimCurve = require("../../src/kit/AnimCurve")
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

type Q = { number }

local function slerp(a: Q, b: Q, u: number): Q
	local dot = a[1] * b[1] + a[2] * b[2] + a[3] * b[3] + a[4] * b[4]
	local sign = if dot < 0 then -1 else 1
	dot = math.abs(dot)
	local wa, wb = 1 - u, u
	if dot < 0.9995 then
		local th = math.acos(dot)
		wa, wb = math.sin((1 - u) * th) / math.sin(th), math.sin(u * th) / math.sin(th)
	end
	local q = {
		wa * a[1] + sign * wb * b[1],
		wa * a[2] + sign * wb * b[2],
		wa * a[3] + sign * wb * b[3],
		wa * a[4] + sign * wb * b[4],
	}
	local n = math.sqrt(q[1] ^ 2 + q[2] ^ 2 + q[3] ^ 2 + q[4] ^ 2)
	return { q[1] / n, q[2] / n, q[3] / n, q[4] / n }
end

local function angle(a: Q, b: Q): number
	local dot = math.clamp(math.abs(a[1] * b[1] + a[2] * b[2] + a[3] * b[3] + a[4] * b[4]), 0, 1)
	return math.deg(2 * math.acos(dot))
end

local function lerp3(a: { number }, b: { number }, u: number): { number }
	return { a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u, a[3] + (b[3] - a[3]) * u }
end

local function dist3(a: { number }, b: { number }): number
	return math.sqrt((a[1] - b[1]) ^ 2 + (a[2] - b[2]) ^ 2 + (a[3] - b[3]) ^ 2)
end

-- the track's value at a time (the line between the keys either side)
local function sample<T>(times: { number }, values: { T }, t: number, lerp: (T, T, number) -> T): T
	local n = #times
	if t <= times[1] then
		return values[1]
	elseif t >= times[n] then
		return values[n]
	end
	for k = 2, n do
		if times[k] >= t then
			return lerp(values[k - 1], values[k], (t - times[k - 1]) / (times[k] - times[k - 1]))
		end
	end
	return values[n]
end

-- what a curve animation plays at key i: the thinned track, sampled by the engine at 30 a second
local function engineAt<T>(times: { number }, values: { T }, kept: { number }, i: number, lerp: (T, T, number) -> T): T
	local kt: { number }, kv: { T } = {}, {}
	for _, k in kept do
		table.insert(kt, times[k])
		table.insert(kv, values[k])
	end
	local g = times[i] * AnimCurve.GRID
	local before, after = math.floor(g) / AnimCurve.GRID, math.ceil(g) / AnimCurve.GRID
	if after == before then
		return sample(kt, kv, times[i], lerp)
	end
	return lerp(sample(kt, kv, before, lerp), sample(kt, kv, after, lerp), g - math.floor(g))
end

local POP = 90 -- degrees in one frame: a broken frame, not motion

local out = {}
for i = 2, #process.args do
	local path = process.args[i]
	local ok, clip = pcall(function()
		return serde.decode("json", fs.readFile(path))
	end)
	if not ok or type(clip) ~= "table" or type(clip.times) ~= "table" or type(clip.joints) ~= "table" then
		out[path] = { error = "not a clip" }
		continue
	end
	local times: { number } = clip.times
	local fps = tonumber(clip.fps) or 30
	local eventFrames: { number } = {}
	for _, ev in clip.events or {} do
		if type(ev) == "table" and type(ev.t) == "number" then
			table.insert(eventFrames, math.clamp(math.floor(ev.t * fps + 0.5) + 1, 1, #times))
		end
	end
	local row = {
		frames = #times,
		tracks = 0,
		keys = 0,
		kept = 0,
		lostDeg = 0,
		lostStuds = 0,
		eventDeg = 0,
		eventStuds = 0,
		moving = 0,
		pops = 0,
		popLostDeg = 0,
	}
	local tracks: { any } = {}
	for _, joint in clip.joints do
		table.insert(tracks, joint.frames)
	end
	for _, key in { "grip", "grip_left" } do -- (the weapon's Handle joint: written and thinned by the exporter)
		if type(clip[key]) == "table" then
			table.insert(tracks, clip[key])
		end
	end
	for _, frames in tracks do
		if type(frames) ~= "table" or #frames ~= #times then
			continue
		end
		local rots: { Q }, places: { { number } } = {}, {}
		local turns, slides = false, false
		for k, f in frames do
			rots[k] = { f[1], f[2], f[3], f[4] }
			places[k] = { f[5], f[6], f[7] }
			if angle(rots[k], rots[1]) > 0.01 then -- (a hundredth of a degree: a held pose's float noise is no motion)
				turns = true
			end
			if dist3(places[k], places[1]) > 1e-4 then
				slides = true
			end
		end
		local popped = false
		for k = 2, #rots do
			if angle(rots[k], rots[k - 1]) > POP then
				popped = true
				row.pops += 1
			end
		end
		row.tracks += 1
		row.keys += 2 * #times
		if turns or slides then
			row.moving += 1
		end
		local keptR = AnimCurve.thin(times, rots, AnimCurve.ROT_TOL, slerp, angle)
		local keptP = AnimCurve.thin(times, places, AnimCurve.POS_TOL, lerp3, dist3)
		row.kept += #keptR + #keptP
		local lostDeg = AnimCurve.lost(times, rots, slerp, angle)
		if popped then
			row.popLostDeg = math.max(row.popLostDeg, lostDeg) -- (a broken frame's "loss" is not the compression's price)
		else
			row.lostDeg = math.max(row.lostDeg, lostDeg)
		end
		row.lostStuds = math.max(row.lostStuds, AnimCurve.lost(times, places, lerp3, dist3))
		if not popped then
			for _, e in eventFrames do
				row.eventDeg = math.max(row.eventDeg, angle(rots[e], engineAt(times, rots, keptR, e, slerp)))
				row.eventStuds = math.max(row.eventStuds, dist3(places[e], engineAt(times, places, keptP, e, lerp3)))
			end
		end
	end
	out[path] = row
end
fs.writeFile(process.args[1], serde.encode("json", out))
print(#process.args - 1)

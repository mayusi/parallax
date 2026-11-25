--!strict
-- CutsceneRules (ReplicatedStorage.kit.CutsceneRules) — the pure maths of a cutscene's timeline (src/kit/Cutscene plays
-- it; kit/anim/cutscene.py writes it into KitAnimations.Cutscenes): where an actor's root is, which play is running,
-- how far into its clip the track should be (the hit-stops freeze it), where the camera is, whether an actor is hidden.
-- Times are the scene's seconds; a play's track time stands still through every hit-stop, as the planned frames do.

local CutsceneRules = {}

export type Play = {
	t: number,
	clip: string, -- a KitAnimations clip, or "@idle" / "@hold"
	from: number?, -- seconds into the clip at its start
	len: number?, -- seconds of the clip it plays
	fade: number?,
	kit: boolean?,
}
export type Hit = { t: number, hold: number }
export type CameraKey = { t: number, loc: { number }, target: { number } }

-- one "x y z yaw" row (yaw in radians) -> numbers
function CutsceneRules.row(r: string | { number }): (number, number, number, number)
	if type(r) == "table" then
		return r[1] or 0, r[2] or 0, r[3] or 0, r[4] or 0
	end
	local p = string.split(r, " ")
	return tonumber(p[1]) or 0, tonumber(p[2]) or 0, tonumber(p[3]) or 0, tonumber(p[4]) or 0
end

-- a marked SNAP (a teleport, a camera cut) inside the step from time a to time b: its time, else nil
local function snapIn(marks: { number }?, a: number, b: number): number?
	if not marks then
		return nil
	end
	for _, m in marks do
		if m > a + 1e-6 and m <= b + 1e-6 then
			return m
		end
	end
	return nil
end
CutsceneRules.snapIn = snapIn

-- the root at scene time t: rows every 1/fps s, linear between rows, the yaw the short way round; across a marked
-- JUMP (`jumps`: the times the planner saw a teleport) it is never blended - the old spot until the jump, then the new
-- one. With no marks (an older timeline) a step over `jump` studs (default 2) counts as one.
function CutsceneRules.rootAt(
	rows: { string | { number } },
	fps: number,
	t: number,
	jump: number?,
	jumps: { number }?
): (number, number, number, number)
	local n = #rows
	if n == 0 then
		return 0, 0, 0, 0
	end
	local f = math.clamp(t * fps, 0, n - 1)
	local i = math.floor(f)
	local u = f - i
	local ax, ay, az, ayaw = CutsceneRules.row(rows[i + 1])
	local bx, by, bz, byaw = CutsceneRules.row(rows[math.min(i + 2, n)])
	if jumps then
		local m = snapIn(jumps, i / fps, (i + 1) / fps)
		if m then
			if t < m - 1e-6 then
				return ax, ay, az, ayaw
			end
			return bx, by, bz, byaw
		end
	elseif (bx - ax) ^ 2 + (bz - az) ^ 2 > (jump or 2) ^ 2 then
		return ax, ay, az, ayaw
	end
	local dy = (byaw - ayaw + math.pi) % (2 * math.pi) - math.pi
	return ax + (bx - ax) * u, ay + (by - ay) * u, az + (bz - az) * u, ayaw + dy * u
end

-- the index of the play running at t (plays sorted by t; nil before the first)
function CutsceneRules.segmentAt(plays: { Play }, t: number): number?
	local at: number? = nil
	for i, p in plays do
		if p.t <= t + 1e-6 then
			at = i
		else
			break
		end
	end
	return at
end

-- seconds of hit-stop between scene times a and b
function CutsceneRules.frozenBetween(hits: { Hit }, a: number, b: number): number
	local s = 0
	for _, h in hits do
		local lo, hi = math.max(a, h.t), math.min(b, h.t + h.hold)
		if hi > lo then
			s += hi - lo
		end
	end
	return s
end

-- true while t is inside a hit-stop
function CutsceneRules.inHitstop(hits: { Hit }, t: number): boolean
	for _, h in hits do
		if t >= h.t and t < h.t + h.hold then
			return true
		end
	end
	return false
end

-- where a play's track should be at scene time t: its start point + the scene time since it began, less the hit-stops
-- in between, never past its own length
function CutsceneRules.trackTime(play: Play, hits: { Hit }, t: number): number
	local ran = math.max(0, t - play.t - CutsceneRules.frozenBetween(hits, play.t, t))
	return (play.from or 0) + math.min(ran, play.len or math.huge)
end

-- the camera (loc, target, in the cutscene's space) at t: linear between keys; across a marked CUT (`cuts`: the
-- planner's shot changes) never blended into a pan - the old shot until the cut, then the new one. With no marks (an
-- older timeline) a key step over 3 studs counts as a cut (a hit's shake moves under 2 a step: the KatanaDuel keys,
-- 1.6 at most vs its smallest cut 4.4)
function CutsceneRules.cameraAt(keys: { CameraKey }, t: number, cuts: { number }?): ({ number }, { number })
	local n = #keys
	if n == 0 then
		return { 0, 5, 14 }, { 0, 0, 0 }
	end
	if t <= keys[1].t then
		return keys[1].loc, keys[1].target
	end
	for i = 1, n - 1 do
		local a, b = keys[i], keys[i + 1]
		if t < b.t then
			if cuts then
				local m = snapIn(cuts, a.t, b.t)
				if m then
					if t < m - 1e-6 then
						return a.loc, a.target
					end
					return b.loc, b.target
				end
			else
				local dl = (b.loc[1] - a.loc[1]) ^ 2 + (b.loc[2] - a.loc[2]) ^ 2 + (b.loc[3] - a.loc[3]) ^ 2
				if dl > 9 then
					return a.loc, a.target
				end
			end
			local u = (t - a.t) / math.max(1e-6, b.t - a.t)
			local function lerp(p: { number }, q: { number }): { number }
				return { p[1] + (q[1] - p[1]) * u, p[2] + (q[2] - p[2]) * u, p[3] + (q[3] - p[3]) * u }
			end
			return lerp(a.loc, b.loc), lerp(a.target, b.target)
		end
	end
	return keys[n].loc, keys[n].target
end

-- true while t is inside one of the actor's hidden spans ({ {from, to} })
function CutsceneRules.hiddenAt(spans: { { number } }, t: number): boolean
	for _, s in spans do
		if t >= s[1] and t < s[2] then
			return true
		end
	end
	return false
end

return CutsceneRules

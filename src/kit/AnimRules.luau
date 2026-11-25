--!strict
-- AnimRules (ReplicatedStorage.kit.AnimRules) — the pure maths of three runtime methods of the owner's lists
-- (2026-11-13), for an R6 body (six rigid blocks: a leg cannot bend, it SLIDES in its hip as the loved R6 clips do).
-- No services, no instances; the kit's specs test it in Lune (kit/test/spec/animrules.spec.luau).
--   AnimRules.feet(left, right, limits?)      PROCEDURAL FOOT PLACEMENT: the ground's height under each foot ->
--                                             how far the pelvis drops and each leg slides so both feet stand on it
--   AnimRules.getUpSide(frontDotUp)           ACTIVE RAGDOLL: which get-up a fallen body plays (on its back / front)
--   AnimRules.rootHold(start, now, T, t)      ... the root's own stand-up turn, held back and let go over T (V4)
--   AnimRules.getUpOffset(rag, clip)          ... the turn from the get-up clip's pose to where the ragdoll left a
--                                             joint, taken ONCE when the motors come back
--   AnimRules.getUpFrom(offset, clip, T, t)   ... and the joint's turn t seconds later: the ragdoll's at 0, the clip's
--                                             at T, no jump (the clip may move meanwhile), no overshoot, no speed
--                                             on arrival. AnimRules.getUp(rag, clip, T, t): both, for a still clip
--   AnimRules.crowd(distances, limits?)       CROWDS: how often each of many characters is animated (every frame,
--                                             every 2nd, every 4th, not at all), the nearest first, inside a budget
--   AnimRules.due(every, frame, rank)         ... and whether the character of that rank among its rate is animated
--                                             on this frame (spread, so the work of a frame stays even)
-- THEIR WAY IN (2026-11-14): src/kit/AnimRagdoll.knock blends every get-up with getUpStep (Moves calls it on a
-- knockdown); src/kit/Anim.feet(character) places the feet with feetStep; src/kit/AnimCrowd keeps the crowd's plan
-- (crowdPlan) and Anim.feet asks it whether a character is due. That instance code is Studio-unproven: reading the
-- ground under the feet, a ragdoll's pose off its parts and the camera's distance is a Studio session's proof.
local AnimRules = {}

-- ---------------------------------------------------------------- foot placement
export type FeetLimits = { drop: number?, lift: number?, reach: number? }
export type Feet = { pelvis: number, left: number, right: number, shortLeft: number, shortRight: number }

AnimRules.DROP = 1.0 -- studs the pelvis may drop to let the lower foot reach its ground
AnimRules.LIFT = 1.2 -- studs a leg may slide UP into the torso (the loved R6 clips slide 0.6 to 1.7)
AnimRules.REACH = 0.3 -- studs a leg may slide DOWN out of the hip

-- left / right: the ground's height under that foot, in studs above (+) or below (-) the floor the clip was made
-- for. Returns offsets in studs, all along the body's up: `pelvis` (0 or less) for the whole body, `left` / `right`
-- each leg's slide in its hip; short* = how far that foot still is from its ground (0 = it stands on it; + = the
-- ground is higher than the foot can lift, - = lower than it can reach). When the two grounds are further apart than
-- the legs can make up, the LOWER foot stands and the higher one is short (it sinks into its step).
function AnimRules.feet(left: number, right: number, limits: FeetLimits?): Feet
	-- a limit is a length: never below 0, and one that is not a number is the kit's own
	local function limit(v: number?, own: number): number
		return if v and v == v then math.max(v, 0) else own
	end
	local drop = limit(if limits then limits.drop else nil, AnimRules.DROP)
	local lift = limit(if limits then limits.lift else nil, AnimRules.LIFT)
	local reach = limit(if limits then limits.reach else nil, AnimRules.REACH)
	if left ~= left or right ~= right then -- (no ground found under a foot: stand as the clip says)
		return { pelvis = 0, left = 0, right = 0, shortLeft = 0, shortRight = 0 }
	end
	-- the pelvis only ever drops: it goes down with the LOWER foot, less what that leg can reach by itself
	local low = math.min(left, right)
	local pelvis = math.clamp(low + reach, -drop, 0)
	local l = math.clamp(left - pelvis, -reach, lift)
	local r = math.clamp(right - pelvis, -reach, lift)
	return { pelvis = pelvis, left = l, right = r, shortLeft = left - pelvis - l, shortRight = right - pelvis - r }
end

-- ---------------------------------------------------------------- active ragdoll: the get-up
-- frontDotUp: the torso's FRONT direction dotted with the world's up (+1 = it faces the sky)
function AnimRules.getUpSide(frontDotUp: number): string
	return if frontDotUp >= 0 then "back" else "front"
end

local function qmul(a: { number }, b: { number }): { number }
	return {
		a[4] * b[1] + a[1] * b[4] + a[2] * b[3] - a[3] * b[2],
		a[4] * b[2] - a[1] * b[3] + a[2] * b[4] + a[3] * b[1],
		a[4] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[4],
		a[4] * b[4] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
	}
end

local function qunit(q: { number }): { number }
	local len = math.sqrt(q[1] * q[1] + q[2] * q[2] + q[3] * q[3] + q[4] * q[4])
	if len < 1e-12 then
		return { 0, 0, 0, 1 }
	end
	return { q[1] / len, q[2] / len, q[3] / len, q[4] / len }
end

-- how much of the way is still to go at t of T: 1 at 0, 0 at T, flat at both ends (no speed, no jolt), never rising
function AnimRules.left(T: number, t: number): number
	if T ~= T or t ~= t then
		return 0
	end
	if T <= 1e-6 or t >= T then
		return 0
	end
	if t <= 0 then
		return 1
	end
	local u = t / T
	return 1 - u * u * u * (10 - 15 * u + 6 * u * u)
end

-- THE OFFSET, taken ONCE when the motors come back: rag = the joint's turn as the ragdoll left it, clip = the get-up
-- clip's turn for it at that moment (each { x, y, z, w }, the joint's own Transform). It is the turn from the clip's
-- pose to the ragdoll's, the short way round.
function AnimRules.getUpOffset(rag: { number }, clip: { number }): { number }
	local c = qunit(clip)
	local r = qunit(rag)
	local off = qmul(r, { -c[1], -c[2], -c[3], c[4] }) -- rag = off * clip
	if off[4] < 0 then
		off = { -off[1], -off[2], -off[3], -off[4] }
	end
	return off
end

-- the joint's turn t seconds later: what is left of the offset, laid on the clip's turn NOW (the clip may move while
-- the blend runs: the offset was taken once, so nothing jumps). T: the blend's length in seconds.
function AnimRules.getUpFrom(offset: { number }, clip: { number }, T: number, t: number): { number }
	local c = qunit(clip)
	local s = math.sqrt(offset[1] * offset[1] + offset[2] * offset[2] + offset[3] * offset[3])
	if s < 1e-9 then
		return c
	end
	local half = math.atan2(s, offset[4]) * AnimRules.left(T, t)
	local k = math.sin(half) / s
	return qunit(qmul({ offset[1] * k, offset[2] * k, offset[3] * k, math.cos(half) }, c))
end

-- both in one, for a clip pose that HOLDS STILL through the blend (the straight way from rag to clip). A clip that
-- moves: take getUpOffset once and call getUpFrom each frame.
function AnimRules.getUp(rag: { number }, clip: { number }, T: number, t: number): { number }
	return AnimRules.getUpFrom(AnimRules.getUpOffset(rag, clip), clip, T, t)
end

-- THE ROOT'S OWN TURN through a get-up (LIMITATIONS_FIXES_V4 4.4 / 13.4.3): the Humanoid's GettingUp stands the root
-- up by itself in a few frames, and the body (rigid on the root) snapped upright with it. start = the root's world
-- turn when the motors came back (the body lying), now = its world turn this frame (each { x, y, z, w }). -> the turn
-- to lay on the RootJoint, in the root's own frame: all of the root's turn since the start undone at 0 (the body still
-- lies as the ragdoll left it), none of it at T - eased by AnimRules.left (no jump, no overshoot, arriving still)
function AnimRules.rootHold(start: { number }, now: { number }, T: number, t: number): { number }
	local n = qunit(now)
	local d = qmul({ -n[1], -n[2], -n[3], n[4] }, qunit(start)) -- now * d = start
	if d[4] < 0 then
		d = { -d[1], -d[2], -d[3], -d[4] }
	end
	local s = math.sqrt(d[1] * d[1] + d[2] * d[2] + d[3] * d[3])
	if s < 1e-9 or s ~= s then
		return { 0, 0, 0, 1 }
	end
	local half = math.atan2(s, d[4]) * AnimRules.left(T, t)
	local k = math.sin(half) / s
	return { d[1] * k, d[2] * k, d[3] * k, math.cos(half) }
end

-- ---------------------------------------------------------------- an additive layer every client plays
-- THE ADDITIVE SEEN BY EVERYONE (LIMITATIONS_FIXES_V4 4.4 / 13.4.3, card txjy): a joint's pose does not travel between
-- machines, so an additive layer started on the SERVER (Moves runs there) was seen by nobody - Anim.additive returned
-- at once on a body the machine does not own. The server now writes a CUE on the character (attribute
-- KitAdd_<clip>, it replicates) and every client's watcher plays the layer itself, from where it is by now.
-- additiveCue: the cue -> "<start server time>;<weight>;<speed>;<0|1 loop>"; stopCue: "stop;<server time>".
-- readCue(value, now) -> { at = seconds already in, weight, speed, loop } | "stop" | nil (a cue that is not one)
AnimRules.CUE_PREFIX = "KitAdd_"

local function finite(v: any): boolean
	return type(v) == "number" and v == v and math.abs(v) < math.huge
end

function AnimRules.cueName(clip: any): string?
	if type(clip) ~= "string" or #clip == 0 or #clip > 90 or not string.match(clip, "^[%w_]+$") then
		return nil -- (an attribute's name: letters, digits and _ only)
	end
	return AnimRules.CUE_PREFIX .. clip
end

function AnimRules.additiveCue(start: number, weight: number?, speed: number?, loop: boolean?): string?
	local w, s = weight or 1, speed or 1
	if not (finite(start) and finite(w) and finite(s)) or s <= 0 then
		return nil
	end
	return string.format(
		"%.4f;%.4f;%.4f;%d",
		start,
		math.clamp(w, 0, 1),
		math.clamp(s, 0.01, 10),
		if loop then 1 else 0
	)
end

function AnimRules.stopCue(now: number): string
	return string.format("stop;%.4f", if finite(now) then now else 0)
end

function AnimRules.readCue(
	value: any,
	now: number
): ({ at: number, weight: number, speed: number, loop: boolean } | string)?
	if type(value) ~= "string" or #value > 80 then
		return nil
	end
	local parts = string.split(value, ";")
	if parts[1] == "stop" then
		return "stop"
	end
	if #parts ~= 4 then
		return nil
	end
	local start, w, s, l = tonumber(parts[1]), tonumber(parts[2]), tonumber(parts[3]), parts[4]
	if not (finite(start) and finite(w) and finite(s)) or (l ~= "0" and l ~= "1") or not finite(now) then
		return nil
	end
	return {
		at = math.max(0, now - (start :: number)),
		weight = math.clamp(w :: number, 0, 1),
		speed = math.clamp(s :: number, 0.01, 10),
		loop = l == "1",
	}
end

-- ---------------------------------------------------------------- crowds
export type CrowdLimits = { near: number?, mid: number?, far: number?, full: number?, half: number? }

AnimRules.NEAR, AnimRules.MID, AnimRules.FAR = 40, 90, 180 -- studs from the camera
AnimRules.FULL, AnimRules.HALF = 12, 24 -- how many characters may be animated every frame / every 2nd frame

-- distances[i]: character i's distance from the camera in studs (not a number = not animated). Returns every[i]: 1
-- (every frame), 2, 4, or 0 (not animated: past `far`), and rank[i]: the character's place among those of its rate
-- (1 = the nearest of them; for AnimRules.due). Inside `near` a character asks for 1, inside `mid` for 2, inside
-- `far` for 4; only the `full` NEAREST get 1 and the next `half` get 2 - whoever is over a budget drops to the next
-- rate, never a nearer character before a farther one.
function AnimRules.crowd(distances: { number }, limits: CrowdLimits?): ({ number }, { number })
	local near = if limits and limits.near then limits.near else AnimRules.NEAR
	local mid = if limits and limits.mid then limits.mid else AnimRules.MID
	local far = if limits and limits.far then limits.far else AnimRules.FAR
	local full = if limits and limits.full then limits.full else AnimRules.FULL
	local half = if limits and limits.half then limits.half else AnimRules.HALF
	local function key(i: number): number -- (never "not a number": a sort on one gives no order at all)
		local d = distances[i]
		return if d ~= d then math.huge else d
	end
	local order = table.create(#distances)
	for i = 1, #distances do
		order[i] = i
	end
	table.sort(order, function(a, b)
		local ka, kb = key(a), key(b)
		if ka ~= kb then
			return ka < kb
		end
		return a < b
	end)
	local every = table.create(#distances, 0)
	local rank = table.create(#distances, 0)
	local ones, twos, fours = 0, 0, 0
	for _, i in order do
		local d = distances[i]
		if d ~= d or d > far then
			every[i] = 0
		elseif d <= near and ones < full then
			ones += 1
			every[i], rank[i] = 1, ones
		elseif d <= mid and twos < half then
			twos += 1
			every[i], rank[i] = 2, twos
		else
			fours += 1
			every[i], rank[i] = 4, fours
		end
	end
	return every, rank
end

-- is the character of this `rank` (AnimRules.crowd's second answer) animated on frame `frame` (a running count)?
-- Characters of one rate are spread over its frames by their rank, so each is animated exactly once in every
-- `every` frames and every frame carries the same share of them.
function AnimRules.due(every: number, frame: number, rank: number): boolean
	every = math.floor(every)
	if every <= 0 then
		return false
	end
	return (frame + rank) % every == 0
end

-- ---------------------------------------------------------------- what the runtime callers do each frame
-- THE GET-UP of a whole body, one frame of it (src/kit/AnimRagdoll): offsets[joint] = the joint's offset taken once
-- (AnimRules.getUpOffset) and its slide then ({ x, y, z }); clip[joint] = { turn = { x, y, z, w }, slide = { x, y, z } }
-- as the Animator has it NOW. Returns the same shape: what to write. A joint the clip does not name is left out.
export type JointPose = { turn: { number }, slide: { number } }
export type GetUpOffset = { turn: { number }, slide: { number } }

function AnimRules.getUpStep(
	offsets: { [string]: GetUpOffset },
	clip: { [string]: JointPose },
	T: number,
	t: number
): { [string]: JointPose }
	local out: { [string]: JointPose } = {}
	local k = AnimRules.left(T, t)
	for joint, off in offsets do
		local c = clip[joint]
		if c then
			out[joint] = {
				turn = AnimRules.getUpFrom(off.turn, c.turn, T, t),
				slide = { c.slide[1] + off.slide[1] * k, c.slide[2] + off.slide[2] * k, c.slide[3] + off.slide[3] * k },
			}
		end
	end
	return out
end

-- FOOT PLACEMENT, one frame of it (src/kit/Anim.feet): the offsets move toward what the ground asks at `rate` a
-- second (no snap when a foot crosses a step's edge); dt in seconds. cur: the last frame's { pelvis, left, right }.
function AnimRules.feetStep(
	cur: { number },
	left: number,
	right: number,
	dt: number,
	rate: number?,
	limits: FeetLimits?
): { number }
	local want = AnimRules.feet(left, right, limits)
	local r = if rate and rate == rate and rate > 0 then rate else 12
	local a = if dt ~= dt or dt <= 0 then 0 else 1 - math.exp(-r * dt)
	return {
		cur[1] + (want.pelvis - cur[1]) * a,
		cur[2] + (want.left - cur[2]) * a,
		cur[3] + (want.right - cur[3]) * a,
	}
end

-- ---------------------------------------------------------------- foot placement with contact state (2026-11-15)
-- THE OWNER'S LIMITATIONS LIST (A-R03 / AN-22): "runtime feet are a limited R6 height correction ... does not
-- establish support-normal alignment, planted contact state, pelvis tilt or explicit moving-platform velocity
-- handling". Within what an R6 body has (a one-piece leg and a flat one-stud sole: no ankle to lay on a slope):
--   CONTACT STATE   a foot is "planted" (the clip has it on its floor), in its "swing" (the clip lifts it) or
--                   "unsupported" (planted by the clip, but no ground under it it can stand on: an edge, a hole, a
--                   wall too steep to stand on). ONLY PLANTED FEET CARRY THE PELVIS: a foot swinging over a hole no
--                   longer pulls the body down, and a foot past an edge hangs as the clip has it.
--   SUPPORT NORMAL  a flat sole on a slope stands on the ground's HIGHEST point under it, not under its middle
--                   (the uphill edge no longer digs in); ground steeper than MAX_SLOPE is no support.
--   PELVIS TILT     opt-in (limits.tilt, degrees; 0 = the body stays upright as R6 bodies do): the pelvis leans
--                   with the ground the planted feet stand on, by that much at most.
--   MOVING SUPPORT  a planted foot's offset is led by how fast ITS GROUND'S HEIGHT changes (AnimRules.groundRate:
--                   the height is already measured against the body's own floor, so a body that climbs a ramp, lands
--                   or rides a lift leads nothing; a platform rising under one foot is met, not sunk into).
export type Sample = {
	height: number, -- the ground under the sole's middle, above (+) / below (-) the clip's floor; NaN = none found
	lifted: number, -- how far the CLIP holds this sole above its floor now (the offsets this rule wrote taken out)
	nx: number?, -- the ground's normal there, in the body's own frame (+Y up, -Z ahead); left out = flat
	ny: number?,
	nz: number?,
	vy: number?, -- how fast that ground's HEIGHT is changing (AnimRules.groundRate), studs a second
	-- the ground under the sole's TOE and HEEL (same measure as `height`; NaN = none): a sole is a stud long, and a
	-- step is under its toe half a stud before it is under its middle (seen in Studio 2026-11-15: read at the middle
	-- only, a foot was 0.35 studs inside a 0.6-stud step as it crossed the edge)
	more: { number }?,
	moreSlope: { number }?, -- how steep the ground is at each of those points, degrees (left out: flat)
}
export type StanceLimits = {
	drop: number?,
	lift: number?,
	reach: number?,
	contact: number?, -- studs above the clip's floor under which a foot is planted
	slope: number?, -- the steepest ground a foot can stand on, degrees
	sole: number?, -- half the sole's length, studs
	tilt: number?, -- the most the pelvis leans with the ground, degrees (0: it never does)
}
export type Stance = {
	pelvis: number,
	left: number,
	right: number,
	shortLeft: number,
	shortRight: number,
	stateLeft: string,
	stateRight: string,
	pitch: number, -- radians, + = the body leans back (the ground rises ahead)
	roll: number, -- radians, + = the body leans to its left (the ground rises to its right)
}

AnimRules.CONTACT = 0.15 -- studs above the clip's floor under which a foot is planted (the build's own contact band)
AnimRules.MAX_SLOPE = 50 -- degrees: steeper ground is not stood on (a sole is flat)
AnimRules.SOLE = 0.5 -- studs: half an R6 sole
AnimRules.PLANTED_RATE = 30 -- a second: how fast a PLANTED foot's offset follows its ground (a swinging one: 12)

-- the ground a flat sole stands on: the height under its middle raised to the ground's highest point under the sole
-- -> that height, and the slope in degrees (0 flat, 90 a wall; NaN when there is no ground)
function AnimRules.soleGround(s: Sample, half: number?, limits: StanceLimits?): (number, number)
	local function limit(v: number?, own: number): number
		return if v and v == v then math.max(v, 0) else own
	end
	local lift = limit(if limits then limits.lift else nil, AnimRules.LIFT)
	local drop = limit(if limits then limits.drop else nil, AnimRules.DROP)
	local reach = limit(if limits then limits.reach else nil, AnimRules.REACH)
	local steepest = limit(if limits then limits.slope else nil, AnimRules.MAX_SLOPE)
	-- THE TOE AND THE HEEL: a rigid sole stands on the highest ground under any of it. A point counts when a leg
	-- could step onto it: no more than `lift` above the middle's ground (above that it is a wall in front of the
	-- foot, not ground) - or, with nothing under the middle (the foot half over an edge), within what the body can
	-- reach from its own floor - and when it is ground a sole can stand on (no steeper than the limit)
	local function edges(base: number): number
		local top = base
		local more: { number } = s.more or {}
		local slopes: { number } = s.moreSlope or {}
		for i, h in more do
			local slope = slopes[i]
			if h == h and not (slope and slope == slope and slope > steepest) then
				local from = if base == base then base else 0
				local low = if base == base then -math.huge else -(drop + reach)
				if h - from <= lift and h >= low and (top ~= top or h > top) then
					top = h
				end
			end
		end
		return top
	end
	if s.height ~= s.height then
		local top = edges(0 / 0)
		return top, if top == top then 0 else 0 / 0
	end
	local nx, ny, nz = s.nx or 0, s.ny or 1, s.nz or 0
	local flat = math.sqrt(nx * nx + nz * nz)
	if not (ny > 1e-6) then
		return s.height, 90 -- (a wall, an overhang: nothing a sole stands on)
	end
	local h = if half and half == half then math.max(half, 0) else AnimRules.SOLE
	-- (a square sole's highest ground is at its uphill CORNER: h * (|nx| + |nz|) / ny; never more than a leg can lift)
	local rise = math.min(h * (math.abs(nx) + math.abs(nz)) / ny, lift)
	return math.max(s.height + rise, edges(s.height)), math.deg(math.atan2(flat, ny))
end

-- HOW FAST A FOOT'S GROUND IS MOVING under it: its height (against the body's own floor) now and at the last look,
-- dt seconds apart, both while the foot was planted -> studs a second, 0 when either is missing (the first look
-- after a swing or the air: nothing is led off one sample). Bounded: a height that jumps (an edge) is not a speed.
function AnimRules.groundRate(prev: number?, now: number, dt: number, most: number?): number
	if not prev or prev ~= prev or now ~= now or dt ~= dt or dt <= 0 then
		return 0
	end
	local cap = if most and most == most then math.abs(most) else 20
	local v = (now - prev) / dt
	return if math.abs(v) > cap then 0 else v
end

-- A FOOT'S CONTACT STATE. prev: its state on the last frame (nil at first) - a planted foot stays planted until the
-- clip lifts it TWICE the contact band (no flicker at the band's edge)
function AnimRules.footState(prev: string?, s: Sample, limits: StanceLimits?): string
	local function limit(v: number?, own: number): number
		return if v and v == v then math.max(v, 0) else own
	end
	local band = limit(if limits then limits.contact else nil, AnimRules.CONTACT)
	local lifted = if s.lifted == s.lifted then s.lifted else 0
	local was = prev == "planted" or prev == "unsupported"
	if lifted > (if was then 2 * band else band) then
		return "swing"
	end
	local ground, slope = AnimRules.soleGround(s, if limits then limits.sole else nil, limits)
	local steepest = limit(if limits then limits.slope else nil, AnimRules.MAX_SLOPE)
	local reach = limit(if limits then limits.reach else nil, AnimRules.REACH)
	local drop = limit(if limits then limits.drop else nil, AnimRules.DROP)
	if ground ~= ground or slope > steepest or ground < -(drop + reach) - 1e-9 then
		return "unsupported" -- (no ground, too steep, or further down than the body can go to it)
	end
	return "planted"
end

-- BOTH FEET, with their contact states: what AnimRules.feet gives, but the pelvis is carried by the PLANTED feet
-- only, a foot stands on the highest ground under its sole, an unsupported foot hangs as the clip has it, and the
-- pelvis leans with its ground when asked (limits.tilt)
function AnimRules.stance(
	left: Sample,
	right: Sample,
	prevLeft: string?,
	prevRight: string?,
	limits: StanceLimits?
): Stance
	local function limit(v: number?, own: number): number
		return if v and v == v then math.max(v, 0) else own
	end
	local drop = limit(if limits then limits.drop else nil, AnimRules.DROP)
	local lift = limit(if limits then limits.lift else nil, AnimRules.LIFT)
	local reach = limit(if limits then limits.reach else nil, AnimRules.REACH)
	local half = if limits then limits.sole else nil
	local sl, sr = AnimRules.footState(prevLeft, left, limits), AnimRules.footState(prevRight, right, limits)
	local gl, gr = AnimRules.soleGround(left, half, limits), AnimRules.soleGround(right, half, limits)
	-- the pelvis goes down with the lower PLANTED foot, less what that leg reaches by itself; no planted foot: it stays
	local low = math.huge
	if sl == "planted" then
		low = math.min(low, gl)
	end
	if sr == "planted" then
		low = math.min(low, gr)
	end
	local pelvis = if low == math.huge then 0 else math.clamp(low + reach, -drop, 0)
	local steepest = limit(if limits then limits.slope else nil, AnimRules.MAX_SLOPE)
	local _, slopeL = AnimRules.soleGround(left, half, limits)
	local _, slopeR = AnimRules.soleGround(right, half, limits)
	local function leg(state: string, ground: number, slope: number): (number, number)
		-- (ground too steep to stand on is nothing to reach for either: a foot swinging past a wall keeps the clip's own)
		if state == "unsupported" or ground ~= ground or slope > steepest then
			return 0, 0 -- (it hangs as the clip has it)
		end
		local slide = math.clamp(ground - pelvis, -reach, lift)
		return slide, ground - pelvis - slide
	end
	local l, shortL = leg(sl, gl, slopeL)
	local r, shortR = leg(sr, gr, slopeR)
	-- the lean: the mean normal of the ground the planted feet stand on, never more than limits.tilt
	local pitch, roll = 0, 0
	local most = math.rad(limit(if limits then limits.tilt else nil, 0))
	if most > 0 then
		local nx, ny, nz, n = 0, 0, 0, 0
		if sl == "planted" then
			nx, ny, nz, n = nx + (left.nx or 0), ny + (left.ny or 1), nz + (left.nz or 0), n + 1
		end
		if sr == "planted" then
			nx, ny, nz, n = nx + (right.nx or 0), ny + (right.ny or 1), nz + (right.nz or 0), n + 1
		end
		if n > 0 and ny > 1e-6 then
			-- (the ground rises AHEAD when its normal leans back toward +Z: the body leans back with it)
			pitch = math.clamp(math.atan2(nz, ny), -most, most)
			roll = math.clamp(math.atan2(-nx, ny), -most, most)
		end
	end
	return {
		pelvis = pelvis,
		left = l,
		right = r,
		shortLeft = shortL,
		shortRight = shortR,
		stateLeft = sl,
		stateRight = sr,
		pitch = pitch,
		roll = roll,
	}
end

-- ONE FRAME OF IT (src/kit/Anim.feet): cur = the last frame's { pelvis, left, right, pitch, roll }. A planted foot
-- follows its ground at `plantedRate` a second and is led by how fast that ground moves (vy / plantedRate: what an
-- eased follower lags a moving target by, so a rising platform is met and not sunk into); everything else eases at
-- `rate`. -> the new { pelvis, left, right, pitch, roll }
function AnimRules.stanceStep(
	cur: { number },
	want: Stance,
	left: Sample,
	right: Sample,
	dt: number,
	rate: number?,
	plantedRate: number?
): { number }
	local slow = if rate and rate == rate and rate > 0 then rate else 12
	local fast = if plantedRate
			and plantedRate == plantedRate
			and plantedRate > 0
		then plantedRate
		else AnimRules.PLANTED_RATE
	fast = math.max(fast, slow)
	local ok = dt == dt and dt > 0
	local function toward(from: number, to: number, r: number): number
		return if ok then from + (to - from) * (1 - math.exp(-r * dt)) else from
	end
	local function lead(state: string, s: Sample): number
		local vy = s.vy
		return if ok and state == "planted" and vy and vy == vy then math.clamp(vy / fast, -0.5, 0.5) else 0
	end
	local anyPlanted = want.stateLeft == "planted" or want.stateRight == "planted"
	return {
		toward(cur[1] or 0, want.pelvis, if anyPlanted then fast else slow),
		toward(cur[2] or 0, want.left + lead(want.stateLeft, left), if want.stateLeft == "planted" then fast else slow),
		toward(
			cur[3] or 0,
			want.right + lead(want.stateRight, right),
			if want.stateRight == "planted" then fast else slow
		),
		toward(cur[4] or 0, want.pitch, slow),
		toward(cur[5] or 0, want.roll, slow),
	}
end

-- THE CROWD, one refresh of it (src/kit/AnimCrowd): ids[i] and distances[i] of every tracked character -> for each
-- id { every, rank } (AnimRules.crowd). An id listed twice keeps its nearer entry.
function AnimRules.crowdPlan(ids: { any }, distances: { number }, limits: CrowdLimits?): { [any]: { number } }
	local every, rank = AnimRules.crowd(distances, limits)
	local plan: { [any]: { number } } = {}
	for i, id in ids do
		local had = plan[id]
		if not had or (every[i] ~= 0 and (had[1] == 0 or every[i] < had[1])) then
			plan[id] = { every[i], rank[i] }
		end
	end
	return plan
end

return AnimRules

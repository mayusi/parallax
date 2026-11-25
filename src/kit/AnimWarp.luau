--!strict
-- AnimWarp — THE RULES OF A ROOT TRAVEL THAT MEETS THE WORLD (the owner's limitations list, 2026-11-15, A-R04 / AN-23 /
-- AN-27): a move's root travel is scaled and turned toward a target (AnimLayers.warpFor / warpedRootAt). This module
-- is what was missing around that: (1) SWEPT CLEARANCE - the warp window's travel is cut so it ends short of what
-- stands in its way, and every frame's step (window or not, warp or not) stops short of what it meets; (2) COMMIT /
-- CANCEL - until when a moving or vanished target may still change the warp, and at what rate; (3) BOUNDED
-- RECONCILIATION - what the body does when something else moved it (a knockback, a teleport, the server's
-- correction) while the move travels. AnimWarp.begin / AnimWarp.step are the whole root update as the game runs it.
--
-- PURE: no instances, no services. The caller (src/kit/Anim.luau applyRoot) supplies the cast and the clock.
-- WRITTEN, NEVER SEEN TO MOVE: the rules are spec'd on made-up roots and walls (kit/test/spec/animwarp.spec.luau);
-- what a body does against a real wall, a moving target and a real network delay only a Studio session can show.
-- NOT SWEPT AHEAD OF TIME: the travel before and after the warp's window (only the frame-by-frame stop holds there).
local AnimLayers = require("./AnimLayers")

local AnimWarp = {}

export type Warp = AnimLayers.Warp
export type Limits = {
	commit: number?, -- the fraction of the window (0..1) after which the target is no longer followed
	scaleRate: number?, -- the most the scale may change in a second while it follows (per second)
	turnRate: number?, -- the most the turn may change in a second while it follows (radians per second)
	margin: number?, -- studs the travel stops short of what blocks it
	samples: number?, -- how many pieces the window's path is swept in
	tries: number?, -- how many times the travel is cut and swept again
	hold: number?, -- studs the body may be off its line and still be held to it
	snap: number?, -- studs off its line from which the body's new place is ACCEPTED (it was moved on purpose)
	replan: number?, -- studs the target moves before the window's travel is swept again
}
-- the caster: the body swept from (ax, az) toward (bx, bz) and `extra` studs on -> the studs it gets before it is
-- stopped, or nil when it is free
export type Cast = (ax: number, az: number, bx: number, bz: number, extra: number) -> number?
export type Window = { from: number, to: number, contact: number?, pace: boolean? }
-- how fast the clip is played up to the window's end: `wind` where the body stands, `travel` where it travels
export type Pace = { from: number, to: number, wind: number, travel: number, rates: { number } }
export type Place = { x: number, z: number, yaw: number }
export type State = {
	t: number, -- the clip's time the travel has been taken to
	x: number, -- the travel so far, in the line's own space
	z: number,
	yaw: number,
	line: Place, -- where the clip's own origin stands in the world
	wroteX: number, -- where the body was put last
	wroteZ: number,
	warp: Warp?,
	cap: number, -- the scale a wall cut the window's travel to (math.huge: nothing was cut)
	seenX: number?, -- where the target was when the window was last swept
	seenZ: number?,
}

AnimWarp.COMMIT = 0.5
AnimWarp.SCALE_RATE = 2
AnimWarp.TURN_RATE = math.rad(180)
AnimWarp.MARGIN = 0.5
AnimWarp.SAMPLES = 8
AnimWarp.TRIES = 6 -- (a turned travel nears an oblique wall in a few cuts: measured, 4 on the spec's 35-degree turn)
AnimWarp.HOLD = 0.05
AnimWarp.SNAP = 3
AnimWarp.REPLAN = 0.25
AnimWarp.SLACK = 0.02 -- studs of the margin a swept travel may be short of and still count as free

local function num(v: any, default: number): number
	return if type(v) == "number" and v == v then v else default
end

-- THE ROOT TRACK as the rules read it: one { x, z, yaw } a frame out of the build's rows ("x z yaw" strings, { x, z,
-- yaw } or the full { qx, qy, qz, qw, px, py, pz }), each yaw within half a turn of the one before (a spin's yaw
-- jumps by whole turns in the data: read as it stands, the body would turn the long way round between two frames)
function AnimWarp.rows(raw: { any }): { { number } }
	local out: { { number } } = {}
	local last: number? = nil
	for _, row in raw do
		local x: number?, z: number?, yaw: number? = nil, nil, nil
		if type(row) == "string" then
			local parts = string.split(row, " ")
			x, z, yaw = tonumber(parts[1]) or 0, tonumber(parts[2]) or 0, tonumber(parts[3]) or 0
		elseif type(row) == "table" and #row >= 7 then
			x, z, yaw = num(row[5], 0), num(row[7], 0), 2 * math.atan2(num(row[2], 0), num(row[4], 1))
		elseif type(row) == "table" then
			x, z, yaw = num(row[1], 0), num(row[2], 0), num(row[3], 0)
		end
		if x and z and yaw then
			if last then
				yaw = last + ((yaw - last + math.pi) % (2 * math.pi) - math.pi)
			end
			last = yaw
			table.insert(out, { x, z, yaw })
		end
	end
	return out
end

-- WHERE IN ITS WARP a move is at t: "free" (the window has not begun: the target may still change everything),
-- "steer" (inside the window, before the commit point: the target is followed at a bounded rate), "committed" (the
-- rest of the window: the warp stands, whatever the target does) or "done" (after the window)
function AnimWarp.phase(w: Warp, t: number, limits: Limits?): string
	local commit = math.clamp(num(limits and limits.commit, AnimWarp.COMMIT), 0, 1)
	local to = math.max(w.from, w.to)
	if t < w.from then
		return "free"
	elseif t >= to then
		return "done"
	elseif t < w.from + (to - w.from) * commit then
		return "steer"
	end
	return "committed"
end

-- THE WARP AFTER THE TARGET MOVED (or was lost): `want` is the warp the target's place asks for NOW (nil: there is no
-- target any more). free: what is wanted, at once (nothing has been travelled yet) - a lost target gives the clip's
-- own travel back. steer: toward what is wanted, by at most the rates * dt - a lost target leaves the warp as it is
-- (the body is on its way: it does not swing back). committed / done: unchanged.
function AnimWarp.retarget(cur: Warp?, want: Warp?, t: number, dt: number, limits: Limits?): Warp?
	if not cur then
		-- (no warp was planned: one may only begin before its window does)
		return if want and t < want.from then want else nil
	end
	local phase = AnimWarp.phase(cur, t, limits)
	if phase == "free" then
		return want
	elseif phase ~= "steer" or not want then
		return cur
	end
	local ds = num(limits and limits.scaleRate, AnimWarp.SCALE_RATE) * math.max(0, dt)
	local da = num(limits and limits.turnRate, AnimWarp.TURN_RATE) * math.max(0, dt)
	return {
		from = cur.from,
		to = cur.to,
		scale = cur.scale + math.clamp(want.scale - cur.scale, -ds, ds),
		turn = cur.turn + math.clamp(want.turn - cur.turn, -da, da),
	}
end

-- THE TRAVEL BETWEEN TWO TIMES under the warp as it is NOW: (dx, dz, dyaw) in the space the move started in. Summed
-- frame by frame it is warpedRootAt itself while the warp stands still, and stays continuous when the warp changes
-- under it (a changed warp bends what is still to come, it never moves what was already travelled).
function AnimWarp.advance(root: { { number } }, fps: number, t0: number, t1: number, w: Warp?): (number, number, number)
	local ax, az, ayaw = AnimLayers.warpedRootAt(root, fps, t0, w)
	local bx, bz, byaw = AnimLayers.warpedRootAt(root, fps, t1, w)
	return bx - ax, bz - az, byaw - ayaw
end

-- THE WINDOW'S PATH as points to sweep between: { { x, z } } from the window's start to its end, in the space the
-- move started in
function AnimWarp.path(root: { { number } }, fps: number, w: Warp, samples: number?): { { number } }
	local n = math.max(1, math.floor(num(samples, AnimWarp.SAMPLES)))
	local to = math.max(w.from, w.to)
	local points = {}
	for i = 0, n do
		local x, z = AnimLayers.warpedRootAt(root, fps, w.from + (to - w.from) * i / n, w)
		table.insert(points, { x, z })
	end
	return points
end

local function length(points: { { number } }, before: number?): number
	local total = 0
	for i = 1, #points - 1 do
		if before and i >= before then
			break
		end
		total += math.sqrt((points[i + 1][1] - points[i][1]) ^ 2 + (points[i + 1][2] - points[i][2]) ^ 2)
	end
	return total
end

-- THE SCALE that ends a travel `total` studs long `margin` short of what blocked it `blockedAt` studs in (the path's
-- length is linear in the scale, so the cut is exact for a straight travel and swept again for a turned one)
function AnimWarp.cut(scale: number, total: number, blockedAt: number, margin: number?): number
	if total <= 1e-6 then
		return scale
	end
	local ok = math.max(0, blockedAt - num(margin, AnimWarp.MARGIN))
	return scale * math.clamp(ok / total, 0, 1)
end

-- where along a path (studs from its start) the body is stopped with less than the margin to spare, or nil
local function stopped(points: { { number } }, cast: Cast, margin: number): number?
	local total = length(points)
	for i = 1, #points - 1 do
		local a, b = points[i], points[i + 1]
		if (b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2 > 1e-10 then
			local dist = cast(a[1], a[2], b[1], b[2], margin)
			if dist ~= nil and dist == dist then
				local at = length(points, i) + math.max(0, dist)
				-- (within SLACK of the margin is the margin: a turned travel nears an oblique wall cut by cut and
				-- would never be seen EXACTLY free)
				if at - margin < total - AnimWarp.SLACK then
					return at
				end
			end
		end
	end
	return nil
end

-- SWEPT CLEARANCE BEFORE THE MOVE: the warp whose WINDOW's travel is free of what stands in its way (the path is in
-- the space the move started in; the caster too). The travel is cut to end `margin` short of the first stop and
-- swept again (a turned travel sweeps other ground when it is shorter), at most `tries` times; a travel that still
-- is not free does not travel at all (scale 0: standing still beats sliding into a wall).
-- -> the warp, and how many studs of its travel were cut
function AnimWarp.fit(root: { { number } }, fps: number, w: Warp, cast: Cast, limits: Limits?): (Warp, number)
	local tries = math.max(1, math.floor(num(limits and limits.tries, AnimWarp.TRIES)))
	local margin = num(limits and limits.margin, AnimWarp.MARGIN)
	local samples = limits and limits.samples
	local cur: Warp = { from = w.from, to = w.to, scale = w.scale, turn = w.turn }
	local first = length(AnimWarp.path(root, fps, w, samples))
	for _ = 1, tries + 1 do
		-- (one sweep more than there are cuts: only a travel SEEN free is taken)
		local points = AnimWarp.path(root, fps, cur, samples)
		local at = stopped(points, cast, margin)
		if at == nil then
			return cur, math.max(0, first - length(points))
		end
		cur = {
			from = cur.from,
			to = cur.to,
			scale = AnimWarp.cut(cur.scale, length(points), at, margin),
			turn = cur.turn,
		}
		if cur.scale <= 1e-6 then
			break
		end
	end
	return { from = cur.from, to = cur.to, scale = 0, turn = cur.turn }, first
end

-- SWEPT CLEARANCE FRAME BY FRAME (what moved into the way since the plan, the travel outside the window, and every
-- travel that has no warp): this frame's step (dx, dz), stopped `margin` short of what the cast met `dist` studs
-- along it (nil: free; the cast looks the margin further than the step).
-- -> the step the body may take, and the studs of it that were lost (the caller DROPS them: the body never catches
-- up through the wall later)
function AnimWarp.stepClear(dx: number, dz: number, dist: number?, margin: number?): (number, number, number)
	local len = math.sqrt(dx * dx + dz * dz)
	if dist == nil or dist ~= dist or len <= 1e-9 then
		return dx, dz, 0
	end
	local ok = math.clamp(dist - num(margin, AnimWarp.MARGIN), 0, len)
	local k = ok / len
	return dx * k, dz * k, len - ok
end

-- BOUNDED RECONCILIATION: the body is (ex, ez) studs off the line the move keeps it on (something else moved it).
-- "hold": within `hold` - nothing to do. "pull": off by less than `snap` - the move takes it back to its line (a
-- shove inside a move does not end the move's travel). "accept": off by `snap` or more - it was moved on purpose (a
-- knockback, a teleport, the server's correction): the line moves to where the body is, the travel goes on from there
-- and nothing snaps back.
function AnimWarp.displaced(ex: number, ez: number, limits: Limits?): string
	local off = math.sqrt(ex * ex + ez * ez)
	if off ~= off then
		return "accept" -- (a place that is not a number is nobody's line)
	end
	if off <= num(limits and limits.hold, AnimWarp.HOLD) then
		return "hold"
	elseif off < num(limits and limits.snap, AnimWarp.SNAP) then
		return "pull"
	end
	return "accept"
end

-- WHEN THE MOVE IS CUT SHORT (the track stopped, the body was taken away): the travel ends where the body is. This
-- is the rule's whole text - nothing is undone and nothing is finished for it - so the caller's loop only has to stop.
-- THE BODY AS IT IS SWEPT (LIMITATIONS_FIXES_V4 4.4 / 13.4.3: workspace:Blockcast in Anim.applyRoot): a box the
-- torso's own width and depth (studs; a number that is not one: R6's 2 x 1), turned the way the body faces, from
-- SWEEP_UNDER studs under the root (a step or a ramp under 2.5 studs stays the Humanoid's to climb: an R6 root rides
-- 3 over the floor) to SWEEP_OVER over it (the head's top). The ball it replaced (0.9 studs) was narrower than the
-- shoulders. -> { size = { x, y, z }, up = the box's middle over the root, probe = the smaller box that catches a body
-- already against a wall at the place it would go (a cast does not see what it starts inside) }
AnimWarp.SWEEP_UNDER, AnimWarp.SWEEP_OVER = 0.4, 2.0
function AnimWarp.sweepBox(width: number?, depth: number?): { size: { number }, up: number, probe: { number } }
	local function ok(v: number?, default: number): number
		return if type(v) == "number" and v == v and v > 0.05 and v < 64 then v else default
	end
	local w, d = ok(width, 2), ok(depth, 1)
	local h = AnimWarp.SWEEP_UNDER + AnimWarp.SWEEP_OVER
	return {
		size = { w, h, d },
		up = (AnimWarp.SWEEP_OVER - AnimWarp.SWEEP_UNDER) / 2,
		probe = { w / 2, h, d / 2 },
	}
end

function AnimWarp.cancelled(playing: boolean, hasBody: boolean): boolean
	return not playing or not hasBody
end

-- ---------------------------------------------------------------- timing that follows the distance (AN-14)
-- A warp makes the body cover more ground (a far target) or less (a near one) IN THE SAME TIME: its feet go up to
-- 1.6 times as fast over the floor as the clip drew them, or half as fast. A paced move instead takes the time
-- from - or gives it to - the part of the clip where the body STANDS (the wind-up): a far target is a shorter
-- wind-up and a longer run, a near one a longer wind-up and a quicker step. The time from the start to the
-- window's end (the Hit, unless the move says otherwise) does NOT change, so the server's clock for the move and
-- everything from the window's end on stay where they were. INSIDE the window the clip's own moments (a Swing
-- marker, a sound cued by frame) come earlier or later than an unpaced clip's: by up to about 60 ms on the built
-- clips. Nothing after the window is touched.
-- Bounded: the travel is never played more than PACE_TRAVEL times faster or slower, the wind-up PACE_WIND.
AnimWarp.PACE_TRAVEL = 1.33
AnimWarp.PACE_WIND = 1.5
AnimWarp.PACE_MOVING = 0.25 -- a frame TRAVELS when its step is this share of the window's longest step or more
AnimWarp.PACE_LEAST = 0.05 -- seconds of standing and of travelling there must be to pace anything
AnimWarp.PACE_AGAIN = 0.1 -- the warp's scale moved this much: what is left of the window is paced anew
AnimWarp.PACE_LOW, AnimWarp.PACE_HIGH = 0.5, 2 -- the rate the clock may ask for
AnimWarp.PACE_GAIN = 8 -- a clip a second off its plan is played this much faster (or slower) ...
AnimWarp.PACE_TRIM = 0.4 -- ... by at most this

-- the pace of a clip's window for a warp of `scale`, from the clip's time t0 (0, or where it is) -> nil when there
-- is nothing to pace (no scale to speak of, no wind-up to take the time from, no travel). budget: the seconds it
-- must take (what is left of the plan when it is paced anew); unsaid: the clip's own time from t0 to the window's end
function AnimWarp.pace(
	root: { { number } },
	fps: number,
	window: Window,
	scale: number,
	t0: number?,
	budget: number?
): Pace?
	local from = math.max(0, t0 or 0)
	if scale ~= scale or scale < 0.05 or math.abs(scale - 1) < 0.02 or fps <= 0 or window.to <= from then
		return nil -- (a scale of nothing: a wall cut the travel away - the body stands, there is no run to pay for)
	end
	local first = math.floor(from * fps + 0.5)
	local last = math.min(#root - 1, math.floor(window.to * fps + 0.5)) -- (frames first .. last - 1 are steps)
	if last - first < 2 then
		return nil
	end
	local steps: { number } = {}
	local longest = 0
	for i = first, last - 1 do
		local a, b = root[i + 1], root[i + 2]
		local d = math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2)
		steps[i - first + 1] = d
		if (i + 0.5) / fps >= window.from then
			longest = math.max(longest, d)
		end
	end
	if longest < 1e-4 then
		return nil
	end
	-- travelling or standing, each frame by the three round it (one slow frame in a run is the run's). Travel
	-- BEFORE the window is the clip's own (the warp does not scale it): played as drawn, in nobody's account
	local n = #steps
	local kind: { number } = table.create(n, 0) -- 0 stands, 1 travels, 2 the clip's own
	local still, going, own = 0, 0, 0
	for i = 1, n do
		local votes, of = 0, 0
		for j = math.max(1, i - 1), math.min(n, i + 1) do
			of += 1
			if steps[j] >= AnimWarp.PACE_MOVING * longest then
				votes += 1
			end
		end
		local moves = votes * 2 > of
		if moves and (first + i - 0.5) / fps < window.from then
			kind[i] = 2
			own += 1
		elseif moves then
			kind[i] = 1
			going += 1
		else
			still += 1
		end
	end
	local a, b = still / fps, going / fps
	if a < AnimWarp.PACE_LEAST or b < AnimWarp.PACE_LEAST then
		return nil
	end
	-- the travel's own rate first (so the feet's speed over the floor changes less), then what the wind-up can give
	-- (a window that ends between two frames: the part of a frame after the plan's last is played as drawn)
	local tail = math.max(0, window.to - last / fps)
	local total = (if budget then budget - tail else a + b + own / fps) - own / fps
	local rate = math.clamp(1 / scale, 1 / AnimWarp.PACE_TRAVEL, AnimWarp.PACE_TRAVEL)
	local wind = math.clamp(total - b / rate, a / AnimWarp.PACE_WIND, a * AnimWarp.PACE_WIND)
	local run = math.clamp(total - wind, b / AnimWarp.PACE_TRAVEL, b * AnimWarp.PACE_TRAVEL)
	local rates: { number } = table.create(n, 1)
	for i = 1, n do
		rates[i] = if kind[i] == 1 then b / run elseif kind[i] == 0 then a / wind else 1
	end
	return { from = first / fps, to = last / fps, wind = a / wind, travel = b / run, rates = rates }
end

-- the rate the plan plays the clip at, at its time t (1 outside what is paced)
function AnimWarp.paceRate(p: Pace?, fps: number, t: number): number
	if not p or t < p.from or t >= p.to then
		return 1
	end
	return p.rates[math.clamp(math.floor((t - p.from) * fps) + 1, 1, #p.rates)]
end

-- the seconds the paced part takes to play
function AnimWarp.paceSeconds(p: Pace, fps: number): number
	local s = 0
	for _, r in p.rates do
		s += (1 / fps) / r
	end
	return s
end

-- where the clip is, by the plan, `real` seconds after the plan began (after its end: at the clip's own rate)
function AnimWarp.paceAt(p: Pace, fps: number, real: number): number
	local acc = 0
	for i, r in p.rates do
		local d = (1 / fps) / r
		if acc + d >= real then
			return p.from + (i - 1 + math.max(0, real - acc) / d) / fps
		end
		acc += d
	end
	return p.to + (real - acc)
end

-- THE CLOCK A PACED MOVE IS PLAYED BY, frame by frame. A rate picked from where the clip IS overshoots at every
-- change of rate (the one review: up to 53 ms short of the window's end on uneven frames); this plays
-- the plan's rate and pulls the clip gently back onto the plan when a long frame has thrown it off.
export type PaceClock = {
	pace: Pace?,
	spent: number, -- seconds of the plan used
	left: number?, -- seconds the rest of the window must take
	base: number, -- the speed somebody else plays the clip at (a slow motion, a caller's 1.2)
	set: number?, -- the speed this clock asked for last
	scale: number?, -- the warp's scale the plan was made for
	done: boolean,
}

function AnimWarp.paceClock(): PaceClock
	return { pace = nil, spent = 0, left = nil, base = 1, set = nil, scale = nil, done = false }
end

-- one frame: the clip is at t, `dt` seconds after the frame before, playing at `speed`; the warp's scale now (nil:
-- no warp) -> the speed to play it at from here, or nil to leave it
function AnimWarp.paceStep(
	c: PaceClock,
	root: { { number } },
	fps: number,
	window: Window,
	scale: number?,
	t: number,
	dt: number,
	speed: number
): number?
	if c.done or speed <= 0 then
		return nil -- (a hit-stop holds the clip at 0: its time is nobody's, and it is not started again from here)
	end
	-- a speed this clock did not ask for is somebody else's: a slow motion, a caller's own - the plan runs under it
	local asked = c.set
	if not asked or math.abs(speed - asked) > 1e-3 then
		c.base = speed
	end
	local used = math.max(0, dt) * c.base
	local left = c.left
	if left then
		c.left = left - used
	end
	c.spent += used
	if t >= window.to then
		c.done, c.pace = true, nil
		c.set = nil
		return if asked and math.abs(speed - c.base) > 1e-3 then c.base else nil
	end
	local was = c.scale
	if scale and (not was or math.abs(scale - was) > AnimWarp.PACE_AGAIN) then
		-- the first plan, or the target moved: what is left of the window is paced anew, in the time that is left
		c.left = c.left or (window.to - t)
		c.pace = AnimWarp.pace(root, fps, window, scale, t, c.left)
		c.spent, c.scale = 0, scale
	end
	local p = c.pace
	if not p then
		c.set = nil
		return if asked and math.abs(speed - c.base) > 1e-3 then c.base else nil
	end
	-- the plan's own rate here, trimmed by how far the clip is from where the plan has it (a gentle pull: measured
	-- in Studio, a clock that asked for the whole miss back in one frame swung between its bounds - a speed set
	-- now is felt a frame later)
	local miss = AnimWarp.paceAt(p, fps, c.spent) - t
	local trim = math.clamp(AnimWarp.PACE_GAIN * miss, -AnimWarp.PACE_TRIM, AnimWarp.PACE_TRIM)
	-- (the rate of the frame to come - where the plan will be when this speed is felt - not of the frame gone)
	local ahead = AnimWarp.paceAt(p, fps, c.spent + 1.5 * math.clamp(dt, 1 / 240, 0.1) * c.base)
	local want = c.base * math.clamp(AnimWarp.paceRate(p, fps, ahead) + trim, AnimWarp.PACE_LOW, AnimWarp.PACE_HIGH)
	c.set = want
	return if math.abs(speed - want) > 1e-3 then want else nil
end

-- ---------------------------------------------------------------- the root update, whole
-- a place on the line -> the world (a turn about +Y, as CFrame.Angles(0, yaw, 0) turns it), and back
local function toWorld(line: Place, x: number, z: number): (number, number)
	local c, s = math.cos(line.yaw), math.sin(line.yaw)
	return line.x + x * c + z * s, line.z - x * s + z * c
end

local function toLine(line: Place, wx: number, wz: number): (number, number)
	local c, s = math.cos(line.yaw), math.sin(line.yaw)
	local dx, dz = wx - line.x, wz - line.z
	return dx * c - dz * s, dx * s + dz * c
end

-- is this a window the rules can work with (two numbers, the end after the start)?
function AnimWarp.window(w: any): Window?
	if
		type(w) == "table"
		and type(w.from) == "number"
		and type(w.to) == "number"
		and w.from == w.from
		and w.to == w.to
		and w.to > w.from
	then
		return w
	end
	return nil
end

-- the warp a target's place asks for: the window's travel reaches from where the WINDOW begins (not where the clip
-- began) to `contact` short of the target
function AnimWarp.wanted(root: { { number } }, fps: number, window: Window, line: Place, tx: number, tz: number): Warp
	local ax, az = AnimLayers.rootSample(root, fps, window.from)
	local bx, bz = AnimLayers.rootSample(root, fps, window.to)
	local lx, lz = toLine(line, tx, tz)
	local rx, rz = lx - ax, lz - az
	local scale, turn = AnimLayers.warpFor(
		math.sqrt((bx - ax) ^ 2 + (bz - az) ^ 2),
		math.sqrt(rx * rx + rz * rz),
		math.atan2(-rx, -rz), -- + = the target is to the left (the clip walks -Z)
		window.contact
	)
	return { from = window.from, to = window.to, scale = scale, turn = turn }
end

-- the window's travel planned for a target and swept (the caster works in the world: the path is taken there)
local function planned(
	s: State,
	root: { { number } },
	fps: number,
	window: Window,
	tx: number,
	tz: number,
	cast: Cast?,
	limits: Limits?
): Warp
	local plan = AnimWarp.wanted(root, fps, window, s.line, tx, tz)
	s.seenX, s.seenZ, s.cap = tx, tz, math.huge
	if not cast then
		return plan
	end
	local line = s.line
	local got, cut = AnimWarp.fit(root, fps, plan, function(ax, az, bx, bz, extra)
		local wax, waz = toWorld(line, ax, az)
		local wbx, wbz = toWorld(line, bx, bz)
		return cast(wax, waz, wbx, wbz, extra)
	end, limits)
	if cut > 1e-6 then
		s.cap = got.scale
	end
	return got
end

-- A MOVE'S TRAVEL BEGINS: the body stands at `body` (the world; yaw about +Y) while the clip is at t0 (0, or the
-- time it was entered at). target: where the warp reaches for ({ x, z }, the world), if anything.
function AnimWarp.begin(
	root: { { number } },
	fps: number,
	t0: number,
	body: Place,
	window: Window?,
	target: { number }?,
	cast: Cast?,
	limits: Limits?
): State
	local function lineFor(w: Warp?): (Place, number, number, number)
		local x, z, yaw = AnimLayers.warpedRootAt(root, fps, t0, w)
		local line = { x = 0, z = 0, yaw = body.yaw - yaw }
		local ox, oz = toWorld(line, x, z)
		line.x, line.z = body.x - ox, body.z - oz
		return line, x, z, yaw
	end
	local line, x, z, yaw = lineFor(nil)
	local s: State = {
		t = t0,
		x = x,
		z = z,
		yaw = yaw,
		line = line,
		wroteX = body.x,
		wroteZ = body.z,
		warp = nil,
		cap = math.huge,
	}
	if window and target and t0 < window.to then
		-- (planned on the clip's own line; a clip entered inside its window then stands on the warped one)
		s.warp = planned(s, root, fps, window, target[1], target[2], cast, limits)
		s.line, s.x, s.z, s.yaw = lineFor(s.warp)
	end
	return s
end

-- ONE FRAME OF A MOVE'S TRAVEL: the clip is at t, `dt` seconds after the last frame, the body is at (hereX, hereZ).
-- -> where the body goes (x, z in the world, yaw about +Y). The state is changed in place.
function AnimWarp.step(
	s: State,
	root: { { number } },
	fps: number,
	t: number,
	dt: number,
	hereX: number,
	hereZ: number,
	window: Window?,
	target: { number }?,
	cast: Cast?,
	limits: Limits?
): (number, number, number)
	-- A TRACK WOUND BACK. By a frame or less (a clock that jitters): the body goes back that little with it. By more
	-- (the clip played again from an earlier time while it still plays - a motion set does that): a NEW travel from
	-- where the body stands; it is not carried back along what it travelled (the one review, 2026-11-15)
	if t < s.t - 1.5 / math.max(fps, 1) then
		local x, z, yaw = AnimLayers.warpedRootAt(root, fps, t, s.warp)
		local heading = s.line.yaw + s.yaw
		s.x, s.z, s.yaw, s.t = x, z, yaw, t
		s.line.yaw = heading - yaw
		s.line.x, s.line.z = 0, 0
		local ox, oz = toWorld(s.line, x, z)
		s.line.x, s.line.z = hereX - ox, hereZ - oz
		s.wroteX, s.wroteZ = hereX, hereZ
		return hereX, hereZ, heading
	end
	-- something else moved the body: a small shove is taken back, a move on purpose is where the travel goes on from
	local moved = AnimWarp.displaced(hereX - s.wroteX, hereZ - s.wroteZ, limits) == "accept"
	if moved then
		s.line.x += hereX - s.wroteX
		s.line.z += hereZ - s.wroteZ
		s.wroteX, s.wroteZ = hereX, hereZ
	end
	-- the target is followed until the move commits
	if window and t < window.to then
		local phase = if s.warp then AnimWarp.phase(s.warp, t, limits) else if t < window.from then "free" else "done"
		if phase == "free" then
			if not target then
				s.warp, s.cap, s.seenX, s.seenZ = nil, math.huge, nil, nil
			else
				local far = num(limits and limits.replan, AnimWarp.REPLAN)
				local seenX, seenZ = s.seenX, s.seenZ
				if
					moved
					or not s.warp
					or not seenX
					or not seenZ
					or (target[1] - seenX) ^ 2 + (target[2] - seenZ) ^ 2 > far * far
				then
					s.warp = planned(s, root, fps, window, target[1], target[2], cast, limits)
				end
			end
		elseif phase == "steer" and target then
			local plan = AnimWarp.wanted(root, fps, window, s.line, target[1], target[2])
			plan.scale = math.min(plan.scale, s.cap) -- (what a wall cut is not grown back)
			s.warp = AnimWarp.retarget(s.warp, plan, t, dt, limits)
		end
	end
	local dx, dz, dyaw = AnimWarp.advance(root, fps, s.t, t, s.warp)
	s.t = t
	local bx, bz = toWorld(s.line, s.x, s.z)
	s.x, s.z, s.yaw = s.x + dx, s.z + dz, s.yaw + dyaw
	local ax, az = toWorld(s.line, s.x, s.z)
	-- this frame's step, stopped short of what stands in its way; what it loses is dropped from the line
	local sx, sz = ax - bx, az - bz
	if cast and sx * sx + sz * sz > 1e-12 then
		local margin = num(limits and limits.margin, AnimWarp.MARGIN)
		local okX, okZ, lost =
			AnimWarp.stepClear(sx, sz, cast(s.wroteX, s.wroteZ, s.wroteX + sx, s.wroteZ + sz, margin), margin)
		if lost > 0 then
			s.line.x += okX - sx
			s.line.z += okZ - sz
		end
	end
	s.wroteX, s.wroteZ = toWorld(s.line, s.x, s.z)
	return s.wroteX, s.wroteZ, s.line.yaw + s.yaw
end

return AnimWarp

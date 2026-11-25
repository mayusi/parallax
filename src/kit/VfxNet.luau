-- VfxNet (kit) - the rules of the VFX network route (Vfx.broadcast -> VfxClient), pure: no services, numbers only.
-- The owner's limitations file, F-R03 (2026-11-15): the route sent name / origin / scale / target to EVERY client and
-- each played on arrival - an observer two maps away built the whole effect, and a client whose event came late
-- played it late (the hit-stop after the hit it belonged to).
--
--   AUDIENCE: a broadcast may say a `reach` (studs). The SERVER sends only to players within it of the effect's
--             origin OR of its target (a beam that lands beside you is yours to see); a player with no character is
--             sent it (a spectator's camera can be anywhere).
--   PHASE:    the server stamps the event with its clock (workspace:GetServerTimeNow(), which clients share). The
--             client reads how LATE it arrived, in REAL seconds: under GRACE it plays from the start; later, the
--             effect starts where its own clock would be by then (clockAt: hit-stops hold that clock, slow motion
--             slows it); at or past the effect's REAL length (realLength) it is not played at all.
--
-- What this is NOT: the server's clock is not what an observer SEES - other characters are drawn a little in the past
-- (network delay and smoothing), so an effect started "on the server's time" can lead the attacker on that screen by
-- that much. Only a session with two clients can say how that looks.
local VfxNet = {}

VfxNet.GRACE = 0.1 -- seconds: an arrival this late or less plays from its start (ordinary ping is not a late event)
VfxNet.REACH_MIN = 8 -- studs: a reach under this is a mistake (nobody but the caster would see the effect)
VfxNet.CATCH_STEP = 1 / 30 -- seconds of the effect's clock: the steps a late stage runs forward in
VfxNet.CATCH_MOST = 30 -- real seconds: the most a late start is run forward (an effect later than this starts there)
VfxNet.HOLD = 0.08 -- seconds: a hit-stop's hold when it says none (the stage's own default)
local TICK = 1 / 240 -- real seconds: the step the clock is worked out in

local function isNumber(v: any): boolean
	return type(v) == "number" and v == v and math.abs(v) ~= math.huge
end

-- a broadcast's reach as the route takes it: nil (everyone) unless a finite number, never under REACH_MIN
function VfxNet.reach(v: any): number?
	if not isNumber(v) or v <= 0 then
		return nil
	end
	return math.max(v, VfxNet.REACH_MIN)
end

-- is a place (px, py, pz) in the audience of an effect at (ox, oy, oz) with this reach (nil = everyone is)
function VfxNet.within(ox: number, oy: number, oz: number, px: number, py: number, pz: number, reach: number?): boolean
	if reach == nil then
		return true
	end
	local dx, dy, dz = px - ox, py - oy, pz - oz
	return dx * dx + dy * dy + dz * dz <= reach * reach
end

-- ------------------------------------------------------------------------------- the audience, without a caller
-- (the owner's limitations file, F-R03: the route took a reach, and no caller passed one - every client was still
-- sent everything.) An effect's audience now comes from the effect itself:
--   the caller's      opts.reach: studs; false or "all" = everyone
--   the preset's      "reach": studs at scale 1 (it grows with the play's scale), or "all"
--   the game's        Vfx.setReach(studs): one reach for every effect that says none; Vfx.setReach(false): everyone
--   else the RULE     REACH_SIZES times the effect's own extent (the farthest any layer reaches from its origin, at
--                     this scale), as far as any of its layers says it is heard or felt (a sound's radius), and
--                     never under REACH_FLOOR: an effect a few studs across is not sent across a map
VfxNet.REACH_FLOOR = 300
VfxNet.REACH_SIZES = 12

local function span(v: any): number -- the most a number, a [x, y, z] or keys [[u, value], ...] reaches
	if isNumber(v) then
		return math.abs(v)
	end
	if type(v) ~= "table" then
		return 0
	end
	local most, sq, flat = 0, 0, true
	for _, k in v do
		if isNumber(k) then
			sq += k * k
		else
			flat = false
			most = math.max(most, span(if type(k) == "table" then k[2] else nil))
		end
	end
	return if flat then math.sqrt(sq) else most
end

-- the farthest a preset's layers reach from the effect's origin, at scale 1 (studs): where a layer is or aims, plus
-- how big it is there (a light's range, a mark's or a crater's size, a mesh's scale) -> (the extent, the farthest any
-- layer says it is HEARD or FELT). A sound's, a screen grade's, a shake's "radius" is already a distance to who gets
-- it - it is not a size to be multiplied (a sound heard at 2600 studs made the rule 31200: everyone)
local FELT =
	{ sound = true, screen = true, shake = true, fov = true, impact = true, world = true, lens = true, grade = true }
function VfxNet.extent(layers: any): (number, number)
	local most, felt = 0, 0
	if type(layers) ~= "table" then
		return most, felt
	end
	for _, el in layers do
		if type(el) == "table" then
			local at = math.max(span(el.point), span(el.aim), span(el.to), span(el.from))
			-- (a version 1 / 2 element says its kind as "type")
			local kind = if type(el.kind) == "string" then el.kind else el.type
			if FELT[kind] then
				felt = math.max(felt, at + span(el.radius))
				most = math.max(most, at)
			else
				local size = math.max(
					span(el.range),
					span(el.size) / 2,
					span(el.radius),
					if kind == "mesh" then span(el.scale) else 0
				)
				most = math.max(most, at + size)
			end
		end
	end
	return most, felt
end

-- who an event is sent to: a reach in studs, or nil for everyone. asked: the caller's (a number, false / "all", or
-- nil); own: the preset's "reach" (a number at scale 1, "all", or nil); game: Vfx.setReach's (a number, false, nil);
-- felt: the farthest a layer says it is heard or felt (extent's second value). Only false or "all" mean everyone: a
-- reach that is no reach (0, a negative, true, a string - a typo) is as if none was given, never a send to all
function VfxNet.audience(asked: any, own: any, game: any, scale: any, extent: any, felt: any): number?
	-- (the client plays a scale within 0.1 to 10: the reach is counted with the same)
	local k = if isNumber(scale) and scale > 0 then math.clamp(scale, 0.1, 10) else 1
	if asked == false or asked == "all" then
		return nil
	end
	if isNumber(asked) and asked > 0 then
		return VfxNet.reach(asked)
	end
	if own == "all" then
		return nil
	end
	if isNumber(own) and own > 0 then
		return VfxNet.reach(own * k)
	end
	if game == false then
		return nil
	end
	if isNumber(game) and game > 0 then
		return VfxNet.reach(game)
	end
	return math.max(
		VfxNet.REACH_FLOOR,
		VfxNet.REACH_SIZES * (if isNumber(extent) then extent else 0) * k,
		(if isNumber(felt) then felt else 0) * k
	)
end

-- THOSE WHO COME INTO REACH LATER (F-R03: "a player who walks into reach after the event never sees the effect").
-- The server keeps every event that went to an audience for as long as the effect REALLY lasts (VfxNet.realLength);
-- `newcomers` is asked a few times a second with where everyone is, and names who has come within reach of an event
-- they were not sent - they are sent it with its ORIGINAL stamp, so their client starts the effect where its clock
-- is by now (catchUp). An event whose time is over is dropped.
--   live: the list ({ id, x, y, z, tx, ty, tz (a target, or nil), reach, over (the clock time it ends), to = { [who] = true } })
--   places: { [who] = { x, y, z } } - or false for someone with no character
--   first: true at the event's own send - someone with no character is in the audience THEN (a spectator's camera can
--          be anywhere); LATER they are not (one who has just joined would be sent every effect on the map at once,
--          each caught up in one frame)
-- -> { { who, event } } to send, in the list's order; `live` loses its ended events and each event learns who it went to
function VfxNet.newcomers(live: { any }, now: number, places: { [any]: any }, first: boolean?): { { any } }
	local out = {}
	for i = #live, 1, -1 do
		if now >= live[i].over then
			table.remove(live, i)
		end
	end
	for _, ev in live do
		for who, at in places do
			if ev.to[who] then
				continue
			end
			local near
			if at == false then
				near = first == true
			else
				near = VfxNet.within(ev.x, ev.y, ev.z, at[1], at[2], at[3], ev.reach)
					or (ev.tx ~= nil and VfxNet.within(ev.tx, ev.ty, ev.tz, at[1], at[2], at[3], ev.reach))
			end
			if near then
				ev.to[who] = true
				table.insert(out, { who, ev })
			end
		end
	end
	return out
end

-- the speed of an effect's clock at its own time t (preset.timewarp: [[t, rate], ...]; 1 outside its keys): the
-- stage's own reading
local function rateAt(warp: any, t: number): number
	if type(warp) ~= "table" or #warp == 0 then
		return 1
	end
	if t < warp[1][1] or t > warp[#warp][1] then
		return 1
	end
	for i = 1, #warp - 1 do
		local a, b = warp[i], warp[i + 1]
		if t <= b[1] then
			return a[2] + (b[2] - a[2]) * ((t - a[1]) / math.max(1e-6, b[1] - a[1]))
		end
	end
	return 1
end

-- the effect's clock run for `age` REAL seconds (age nil: until the effect ends) -> (its time, what is left of a hold
-- it is in, the real seconds it took). hitstop: [{ at, hold }] freezes the clock for `hold` real seconds as it crosses
-- `at`; timewarp slows it. The stage's own step, in numbers
local function run(age: number?, duration: number, hitstop: any, warp: any): (number, number, number)
	local t, used = 0, 0
	local hits = if type(hitstop) == "table" then hitstop else {}
	local budget = if age then age else 600
	while used < budget - 1e-9 and t < duration do
		local dt = math.min(TICK, budget - used)
		local rate = math.max(rateAt(warp, t), 1e-3)
		local nt = t + dt * rate
		local hit: any = nil
		for _, h in hits do
			if type(h) == "table" and isNumber(h.at) and t < h.at and nt >= h.at then
				hit = h
				break
			end
		end
		if hit then
			used += (hit.at - t) / rate
			t = hit.at
			local hold = if isNumber(hit.hold) then math.max(hit.hold, 0) else VfxNet.HOLD
			if used + hold > budget then
				return t, used + hold - budget, budget
			end
			used += hold
		else
			t = nt
			used += dt
		end
	end
	return math.min(t, duration), 0, used
end

-- how long an effect really plays, in REAL seconds: its duration, its hit-stops' holds and its slow motion together
-- (math.huge for an effect with no end; 600 at most)
function VfxNet.realLength(duration: any, hitstop: any, warp: any): number
	if duration == math.huge then
		return math.huge
	end
	if not isNumber(duration) or duration <= 0 then
		return 0
	end
	local _, _, used = run(nil, duration, hitstop, warp)
	return used
end

-- where an effect's own clock is `age` real seconds after it started -> (its time, the real seconds left of a hold it
-- is in). age is taken as CATCH_MOST at most
function VfxNet.clockAt(age: any, duration: any, hitstop: any, warp: any): (number, number)
	if not isNumber(age) or age <= 0 then
		return 0, 0
	end
	local length = if duration == math.huge
		then math.huge
		elseif isNumber(duration) and duration > 0 then duration
		else 0
	local t, left = run(math.min(age, VfxNet.CATCH_MOST), length, hitstop, warp)
	return t, left
end

-- what a client does with an event stamped `sent` that it reads at `now` (both the shared server clock), for an effect
-- that really plays `length` seconds (realLength): "play" (from its start), "late" (start `age` REAL seconds in),
-- "drop" (it is over) -> (what, age)
function VfxNet.phase(sent: any, now: any, length: any): (string, number)
	if not isNumber(sent) or not isNumber(now) then
		return "play", 0 -- no stamp (an older server), or no clock: as before
	end
	local age = now - sent
	if age <= VfxNet.GRACE then
		return "play", 0 -- (a stamp from the future is a clock a little off: from the start)
	end
	if length ~= math.huge and (not isNumber(length) or age >= length) then
		return "drop", age
	end
	return "late", age
end

-- the steps of the EFFECT's clock a late stage takes to reach time `to`: whole CATCH_STEPs and the rest
function VfxNet.catchUp(to: any): { number }
	local steps: { number } = {}
	if not isNumber(to) or to <= 0 then
		return steps
	end
	local left = to
	while left > 1e-9 and #steps < 2000 do
		local d = math.min(left, VfxNet.CATCH_STEP)
		table.insert(steps, d)
		left -= d
	end
	return steps
end

-- HOW FAR ONE STEP MOVES AN EFFECT'S CLOCK. Roblox's Heartbeat hands a step the duration of the PREVIOUS frame (its
-- dt), so an effect made inside a long frame - the avatar arriving hitches a client 0.3 to 1.3 s - would jump that
-- far into its life on its first step (seen in Studio, 2026-11-16: 1.35 s of an effect gone 0.02 s after it was
-- played). A step moves the clock by the frame's dt but never by more than the real time since the last step (or
-- since the effect was made): -> (the step, the clock to remember for the next). dt and the clocks are seconds
function VfxNet.stepBy(dt: number, now: number, last: number): (number, number)
	local real = math.max(0, now - last)
	local d = if type(dt) == "number" and dt == dt and dt > 0 then math.min(dt, real) else 0
	return d, now
end

return VfxNet

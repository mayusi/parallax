--!strict
-- AnimBlend (ReplicatedStorage.kit.AnimBlend) — the pure maths of the kit's locomotion blend: for a move direction
-- (in the character's own space), a speed and the clips' measured ground speeds, which clips play at what WEIGHT
-- (summing to 1) and at what RATE (so the planted foot moves back at the character's real speed). No services, no
-- instances: Anim.locomotion drives it every frame; the kit's specs test it in Lune.
local AnimBlend = {}

export type Set = {
	idle: string?,
	walk: string?,
	run: string?,
	back: string?,
	strafeLeft: string?,
	strafeRight: string?,
	jump: string?,
	fall: string?,
	land: string?,
	-- the moments BETWEEN the loops (AnimBlend.transition): each a one-shot laid over the blend, entered at the
	-- frame nearest the pose the body is in when its clip carries a pose table ("match": {"pose": true})
	start: string?, -- from standing to moving
	stop: string?, -- from moving to standing (the settle after the body halts)
	pivot: string?, -- the way it goes reversed
	turnLeft: string?, -- standing, the body turning on the spot
	turnRight: string?,
}
export type ClipMeta = { speed: number?, duration: number?, loop: boolean? }
export type Meta = { [string]: ClipMeta }
export type Play = { weight: number, rate: number }

AnimBlend.IDLE_SPEED = 0.5 -- studs/s under which the character idles
AnimBlend.MIN_RATE, AnimBlend.MAX_RATE = 0.5, 3.0

local function groundSpeed(meta: Meta, name: string?, fallback: number): number
	local m = if name then meta[name] else nil
	return if m and type(m.speed) == "number" and m.speed > 0 then m.speed else fallback
end

-- localMove: the move direction in the character's space (x = right, z = forward is NEGATIVE, Roblox axes),
-- unit length or zero; speed: studs/s along the ground. Returns { [clipName] = { weight, rate } } for every clip
-- of the set that should be playing (others: weight 0).
function AnimBlend.weights(set: Set, meta: Meta, localMove: Vector3, speed: number): { [string]: Play }
	local out: { [string]: Play } = {}
	-- a clip asked for twice (the walk standing in for a back AND a strafe) blends its SIGNED rates by weight,
	-- so a mostly-backward diagonal still plays it in reverse; rates are clamped once, at the end
	local function add(name: string?, weight: number, rate: number)
		if name and weight > 1e-4 then
			local cur = out[name]
			local w = (if cur then cur.weight else 0) + weight
			out[name] = { weight = w, rate = ((if cur then cur.weight * cur.rate else 0) + weight * rate) / w }
		end
	end
	local function clamped(): { [string]: Play }
		for _, play in out do
			-- (a rate of exactly 0 - a walk asked for backwards and sideways in equal parts - is a statue: it plays forward)
			local sign = if play.rate < 0 then -1 else 1
			play.rate = sign * math.clamp(math.abs(play.rate), AnimBlend.MIN_RATE, AnimBlend.MAX_RATE)
		end
		return out
	end
	if speed < AnimBlend.IDLE_SPEED or localMove.Magnitude < 1e-3 then
		add(set.idle, 1, 1)
		return clamped()
	end
	local dir = localMove.Unit
	local fwd, bwd = math.max(0, -dir.Z), math.max(0, dir.Z)
	local left, right = math.max(0, -dir.X), math.max(0, dir.X)
	local total = fwd + bwd + left + right
	if total < 1e-6 then -- straight up or down: no ground direction to walk in
		add(set.idle, 1, 1)
		return clamped()
	end
	fwd, bwd, left, right = fwd / total, bwd / total, left / total, right / total
	-- forward: walk and run cross-fade by speed between their natural ground speeds
	local walkSpeed = groundSpeed(meta, set.walk, 8)
	local runSpeed = groundSpeed(meta, set.run, 16)
	local t = if set.run and set.walk
		then math.clamp((speed - walkSpeed) / math.max(runSpeed - walkSpeed, 0.1), 0, 1)
		elseif set.run then 1
		else 0
	add(set.walk, fwd * (1 - t), speed / walkSpeed)
	add(set.run or set.walk, fwd * t, speed / (if set.run then runSpeed else walkSpeed))
	-- backward and sideways: their own clips, or the walk (or the run) when the set has none — a walk played
	-- BACKWARDS (a negative rate) moves its planted foot the right way; a strafe has no such trick
	local ground = set.walk or set.run
	local fallback = if set.walk then walkSpeed else runSpeed
	add(set.back or ground, bwd, (if set.back then 1 else -1) * speed / groundSpeed(meta, set.back or ground, fallback))
	add(set.strafeLeft or ground, left, speed / groundSpeed(meta, set.strafeLeft or ground, fallback))
	add(set.strafeRight or ground, right, speed / groundSpeed(meta, set.strafeRight or ground, fallback))
	-- whatever the set lacks, what plays carries the full weight (never a silent character with Animate off)
	local sum = 0
	for _, play in out do
		sum += play.weight
	end
	if sum < 1e-4 then
		add(set.idle, 1, 1)
	elseif math.abs(sum - 1) > 1e-4 then
		for _, play in out do
			play.weight /= sum
		end
	end
	return clamped()
end

-- IN THE AIR (the movement state machine's own rule; Anim.locomotion calls it on every Humanoid state change and
-- every frame): state = the Humanoid state's name ("Jumping", "Freefall", "Landed", any other).
--   AnimBlend.oneShot(set, state)       the clip played ONCE on entering that state: the jump, the land (nil: none)
--   AnimBlend.falling(state)            does that state start (true) or end (false) a fall?
--   AnimBlend.onFoot(state, platformStand, sit)   is the body walking on the ground (not thrown, fallen, seated)?
--   AnimBlend.going(mx, mz, vx, vz, walkSpeed, onFoot)   the way a body is going: what it is asked (MoveDirection),
--                                       or - walked by Humanoid:MoveTo, which asks nothing - the way it moves
--   AnimBlend.airborne(set, falling, wanted)   what plays this frame: the fall alone while falling (when the set has
--                                       one), else the ground blend `wanted` as it is
-- IS THE BODY ON FOOT? state: the Humanoid's state by name. Running, RunningNoPhysics (some server NPCs) and Landed
-- (the few frames after an NPC hops a ledge: without it the walk dips to the idle mid-stride) are on foot. A body
-- whose PlatformStand or Sit is set is not, whatever its state says: a state does not reach every machine (a
-- ragdoll knocked on the server can still read Running elsewhere) and those two properties do.
function AnimBlend.onFoot(state: string, platformStand: boolean, sit: boolean): boolean
	if platformStand or sit then
		return false
	end
	return state == "Running" or state == "RunningNoPhysics" or state == "Landed"
end

-- THE WAY A BODY IS GOING, in the world, length 0..1. (mx, mz): the Humanoid's MoveDirection; (vx, vz): its root's
-- velocity along the ground, MEASURED AGAINST THE FLOOR IT STANDS ON (a body standing still on a conveyor or a
-- moving platform is carried, not going: the caller takes the floor's own velocity off - Anim.going); walkSpeed: the Humanoid's; onFoot: it is walking on the ground (state Running), not
-- thrown, fallen or ragdolled.
-- WHY: Humanoid:MoveTo walks a body with MoveDirection at ZERO - measured in Studio 2026-11-15 on a player's own
-- character and on a server NPC, both moving at their WalkSpeed. Every rule that read MoveDirection alone saw a
-- walking NPC as standing: the idle slid along the ground at 8 and 16 studs a second. So: what the body is asked
-- when it is asked anything; else, on foot and faster than an idle, the way it moves (as fast as it moves against
-- its WalkSpeed, 1 at most); else nothing. A body thrown through the air is not "going" anywhere.
function AnimBlend.going(
	mx: number,
	mz: number,
	vx: number,
	vz: number,
	walkSpeed: number,
	onFoot: boolean
): (number, number)
	if mx == mx and mz == mz and mx * mx + mz * mz > 1e-6 then
		return mx, mz
	end
	local speed = math.sqrt(vx * vx + vz * vz)
	if not onFoot or not (speed >= AnimBlend.IDLE_SPEED and speed < math.huge) then
		return 0, 0
	end
	local share = if walkSpeed == walkSpeed and walkSpeed > 0 then math.min(speed / walkSpeed, 1) else 1
	return vx / speed * share, vz / speed * share
end

-- THE MOMENTS BETWEEN THE LOOPS (the owner's older list, AN-28: "locomotion remains a finite direction / speed
-- blend ... braking, turn-in-place / pivot coverage"). A blend by speed and direction has no word for the instant a
-- body starts, halts, reverses or turns where it stands: the walk simply fades in or out over the idle. This reads
-- those instants off what the body DOES - its velocity OVER THE GROUND IT STANDS ON and how fast it turns - not off
-- what it is asked, so a player's stick and a body walked by Humanoid:MoveTo are read alike. The caller feeds it
-- only while the body is on foot (a flung body, a ragdoll, a rider is not walking: Anim.locomotion starts afresh).
--   "start"       it stood (STILL seconds, two frames or more) and reaches pace within RAMP seconds of standing
--   "stop"        it moved at pace and stands again, the standstill begun within HALT seconds of its last frame at
--                 pace (a body that drifts down slowly has stopped walking, not halted: the blend's fade covers it)
--   "pivot"       at pace, more than 120 degrees round from the way it went about REF seconds ago, kept for
--                 PIVOT_HOLD seconds (two frames or more) - a snap reversal, one through a frame of nothing, a tight
--                 U-turn; a wide curve is the blend's
--   "turnLeft" / "turnRight"   it has stood QUIET seconds and has turned TURN_ANGLE degrees one way at
--                 TURN_RATE or faster. ONE turn a turning: it must stop turning (CALM seconds) before the next -
--                 a camera panned steadily round a standing body is one turn, a shaking one is none.
-- "At pace": half its WalkSpeed or more. One moment at a time (COOL seconds apart, but a start straight after a
-- turn); a moment the wait held back is played when the wait ends if it still holds - a stop is never dropped while
-- its start was played. A single frame that turns the body more than SNAP degrees is a teleport, not a turn.
export type Flow = {
	t: number,
	paceAt: number?, -- when it last moved at pace
	movedAt: number?, -- when it last moved at all (faster than an idle)
	began: boolean, -- a start or a pivot has been played since the last stop (a stop is owed only then)
	hist: { { number } }, -- { t, vx, vz } of its frames at pace, the last WINDOW seconds
	rev: number, -- how long, and for how many frames, it has gone the other way
	revFrames: number,
	still: number, -- how long, and for how many frames, it has stood
	stillFrames: number,
	stoodAt: number?, -- when it last stood (a start is owed until RAMP seconds after)
	halting: boolean, -- this standstill began within HALT seconds of pace (a stop is owed)
	turnSum: number, -- degrees turned one way in this turning, and for how many frames
	turnFrames: number,
	turnDone: boolean, -- this turning has had its moment
	calm: number, -- how long it has not been turning
	cool: number,
	turned: boolean, -- the last moment was a turn on the spot
}

-- (HALT: measured in Studio 2026-11-15 - a body told to stop at 16 studs a second stands 0.40 to 0.53 s later, 3 to
-- 4 studs on; it is under half its WalkSpeed for the second half of that. 0.25 missed two halts of three)
AnimBlend.STILL, AnimBlend.HALT, AnimBlend.RAMP = 0.1, 0.45, 0.5
AnimBlend.PAST, AnimBlend.REF, AnimBlend.WINDOW, AnimBlend.PIVOT_HOLD = 0.15, 0.3, 0.9, 0.08
AnimBlend.TURN_RATE, AnimBlend.TURN_ANGLE, AnimBlend.CALM, AnimBlend.QUIET = 120, 30, 0.15, 0.5
AnimBlend.SNAP, AnimBlend.COOL = 90, 0.35

-- the HALT window for a body's WalkSpeed (the owner's V3 list, anim stage F.1): measured at 16 studs a second, and a
-- faster walker brakes from further, under pace for longer - scaled by WalkSpeed / 16, never shorter than measured
-- (a body at 32 is under its pace of 16 for about twice as long; at 0.45 s its halts were read as drifting to a stop).
-- Not measured in Studio above 16: the proportion is the rule's, said here
function AnimBlend.haltWindow(walkSpeed: number?): number
	local ws = if type(walkSpeed) == "number" and walkSpeed == walkSpeed and walkSpeed > 0 then walkSpeed else 16
	return AnimBlend.HALT * math.clamp(ws / 16, 1, 3)
end

function AnimBlend.flow(): Flow
	return {
		t = 0,
		paceAt = nil,
		movedAt = nil,
		began = false,
		hist = {},
		rev = 0,
		revFrames = 0,
		still = 0,
		stillFrames = 0,
		stoodAt = nil,
		halting = false,
		turnSum = 0,
		turnFrames = 0,
		turnDone = false,
		calm = 0,
		cool = 0,
		turned = false,
	}
end

-- one frame: (vx, vz) the body's velocity over the ground it stands on, yawRate how fast it turns (degrees a
-- second, + = to the left), dt, walkSpeed. Returns the moment that began this frame (a key of Set) or nil.
-- Mutates `flow`.
function AnimBlend.transition(
	flow: Flow,
	vx: number,
	vz: number,
	yawRate: number,
	dt: number,
	walkSpeed: number
): string?
	if vx ~= vx or vz ~= vz or dt ~= dt or not (dt > 0) then
		return nil
	end
	flow.t += dt
	flow.cool = math.max(flow.cool - dt, 0)
	local t = flow.t
	local speed = math.sqrt(vx * vx + vz * vz)
	local pace =
		math.max((if walkSpeed == walkSpeed and walkSpeed > 0 then walkSpeed else 16) * 0.5, 2 * AnimBlend.IDLE_SPEED)
	local yaw = if yawRate == yawRate and math.abs(yawRate * dt) <= AnimBlend.SNAP then yawRate else 0
	local event: string? = nil
	local function resetTurn()
		flow.turnSum, flow.turnFrames, flow.turnDone, flow.calm = 0, 0, false, 0
	end
	if speed >= pace then
		-- the way it went a moment ago (PAST .. WINDOW seconds, at pace): the newest such frame
		while #flow.hist > 0 and t - flow.hist[1][1] > AnimBlend.WINDOW do
			table.remove(flow.hist, 1)
		end
		-- (the frame nearest REF seconds ago: far enough back that a U-turn of half a second has turned past 120
		-- degrees since, near enough that a wide curve has not. After a gap - it slowed through nothing - the last
		-- frame before the gap)
		local ref: { number }? = nil
		for i = 1, #flow.hist do
			local age = t - flow.hist[i][1]
			if age <= AnimBlend.REF and age >= AnimBlend.PAST then
				ref = flow.hist[i]
				break
			end
		end
		if not ref then
			for i = #flow.hist, 1, -1 do
				if t - flow.hist[i][1] >= AnimBlend.PAST then
					ref = flow.hist[i]
					break
				end
			end
		end
		local back = false
		if ref then
			local was = math.sqrt(ref[2] * ref[2] + ref[3] * ref[3])
			back = was > 0 and (vx * ref[2] + vz * ref[3]) / (speed * was) < -0.5
		end
		if back then
			flow.rev += dt
			flow.revFrames += 1
			if flow.rev >= AnimBlend.PIVOT_HOLD and flow.revFrames >= 2 then
				if flow.cool <= 0 then
					event = "pivot"
				end
				flow.hist = {} -- (the way it goes now is the way it goes)
				flow.rev, flow.revFrames = 0, 0
				back = false
			end
		else
			flow.rev, flow.revFrames = 0, 0
		end
		if not back then
			table.insert(flow.hist, { t, vx, vz }) -- (while it is turning back the old way is kept to measure against)
		end
		-- (a body takes a few frames to reach pace: the start is owed from when it last stood, for RAMP seconds; one
		-- that turned round where it stood and walks off has started - the turn does not hold the start back)
		local stoodAt = flow.stoodAt
		if stoodAt then
			if t - stoodAt > AnimBlend.RAMP then
				flow.stoodAt = nil
			elseif not event and (flow.cool <= 0 or flow.turned) then
				event = "start"
				flow.stoodAt = nil
			end
		end
		flow.paceAt = t
		flow.movedAt = t
		flow.halting = false
		flow.still, flow.stillFrames = 0, 0
		resetTurn()
	elseif speed < AnimBlend.IDLE_SPEED then
		flow.rev, flow.revFrames = 0, 0
		if flow.stillFrames == 0 then -- (this standstill begins: within HALT seconds of pace it is a halt)
			local paceAt = flow.paceAt
			flow.halting = paceAt ~= nil and t - paceAt <= AnimBlend.haltWindow(walkSpeed)
		end
		flow.still += dt
		flow.stillFrames += 1
		-- (a halt is a body that STAYS still - STILL seconds and two frames: the engine passes through a frame of
		-- nothing in a reversal too, and one long frame is not a standstill)
		if flow.still >= AnimBlend.STILL and flow.stillFrames >= 2 then
			flow.stoodAt = t
			if flow.halting and not flow.began then
				flow.halting = false -- (its start was never played: neither is its stop)
			elseif flow.halting and flow.cool <= 0 then
				event = "stop"
				flow.halting = false
			end
		end
		-- (it has STOOD for QUIET seconds: a body that has just come to rest - from a run or from a slow walk -
		-- often swings round as it settles, and that is the halt's)
		local movedAt = flow.movedAt
		local quiet = movedAt == nil or t - movedAt > AnimBlend.QUIET
		if math.abs(yaw) >= AnimBlend.TURN_RATE then
			if flow.turnSum ~= 0 and (yaw > 0) ~= (flow.turnSum > 0) then
				flow.turnSum, flow.turnFrames = 0, 0 -- (the other way: a shake, not a turn)
			end
			flow.turnSum += yaw * dt
			flow.turnFrames += 1
			flow.calm = 0
			if
				not event
				and not flow.turnDone
				and quiet
				and not flow.halting
				and math.abs(flow.turnSum) >= AnimBlend.TURN_ANGLE
				and flow.turnFrames >= 2
				and flow.cool <= 0
			then
				event = if flow.turnSum > 0 then "turnLeft" else "turnRight"
				flow.turnDone = true
			end
		else
			flow.calm += dt
			if flow.calm >= AnimBlend.CALM then
				resetTurn()
			end
		end
	else
		-- between standing and pace: neither
		flow.movedAt = t
		flow.rev, flow.revFrames = 0, 0
		flow.still, flow.stillFrames = 0, 0
		flow.halting = false
		resetTurn()
	end
	if event then
		flow.cool = AnimBlend.COOL
		flow.turned = event == "turnLeft" or event == "turnRight"
		if event == "start" or event == "pivot" then
			flow.began = true
		elseif event == "stop" then
			flow.began = false
		end
	end
	return event
end

function AnimBlend.oneShot(set: Set, state: string): string?
	if state == "Jumping" then
		return set.jump
	elseif state == "Landed" then
		return set.land
	end
	return nil
end

function AnimBlend.falling(state: string): boolean
	return state == "Freefall" -- any other state (climbing, swimming, seated, landed) ends the fall
end

function AnimBlend.airborne(set: Set, falling: boolean, wanted: { [string]: Play }): { [string]: Play }
	if falling and set.fall then
		return { [set.fall] = { weight = 1, rate = 1 } }
	end
	return wanted
end

return AnimBlend

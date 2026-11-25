--!strict
-- AnimLayers — the runtime layers pros put on top of keyed animation, as pure maths (AAA gaps v2 wave 3/4;
-- board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md). Instance code lives in Anim / Moves / AnimSecondary / AnimRagdoll;
-- everything here is numbers so the spec can prove it outside Roblox.
--
--   inertial(x0, v0, T, t)          D1  INERTIALIZATION (Bollo, GDC 2018 "Inertialization: High-Performance Animation
--                                       Transitions in Gears of War"): a transition is the new pose plus an OFFSET
--                                       that decays to 0 over T on a quintic - no cross-fade mush, no pop
--   warpedRootAt(root, fps, t, w)   C5  MOTION WARPING: inside the warp window the root track's travel is scaled and
--                                       turned so the attack reaches its target (UE5 Motion Warping / "freeflow")
--   warpFor(...)                        the scale + turn a target asks for, clamped
--   reactionSide(attacker, victim)  C4  which side of the victim the blow came from: Front / Back / Left / Right
--   turnAllowed(phase, track)       C6  TRACKING + COMMITMENT: turning allowed in startup, locked in active
--   kick(t, amp, halflife)          D9  a camera kick along the blow: an instant offset decaying like a spring
--   swing(s, accel, dt, k)          D7  SECONDARY MOTION: a damped spring an accessory hangs on

local AnimLayers = {}

-- ---------------------------------------------------------------- D1 inertialization
-- the offset at time t of a transition that started with offset x0 (any unit) moving at v0 (per second), decaying to
-- exactly 0 at T with zero velocity and acceleration (Bollo's quintic; v0 toward the target is kept, away is clamped)
function AnimLayers.inertial(x0: number, v0: number, T: number, t: number): number
	if T <= 1e-6 or t >= T then
		return 0
	end
	if t <= 0 then
		return x0
	end
	local sign = if x0 < 0 then -1 else 1
	local x, v = x0 * sign, v0 * sign
	if v > 0 then
		v = 0 -- moving AWAY from the target pose: the blend never overshoots by keeping it
	end
	if x <= 1e-9 then
		return 0
	end
	-- the blend time cannot be shorter than the velocity can reach 0 in (Bollo: T = min(T, -5 x0 / v0))
	if v < 0 then
		T = math.min(T, -5 * x / v)
	end
	if t >= T then
		return 0
	end
	local a0 = math.max(0, (-8 * v * T - 20 * x) / (T * T))
	local A = -(a0 * T * T + 6 * v * T + 12 * x) / (2 * T ^ 5)
	local B = (3 * a0 * T * T + 16 * v * T + 30 * x) / (2 * T ^ 4)
	local C = -(3 * a0 * T * T + 12 * v * T + 20 * x) / (2 * T ^ 3)
	local y = A * t ^ 5 + B * t ^ 4 + C * t ^ 3 + (a0 / 2) * t * t + v * t + x
	return y * sign
end

-- THE OFFSET'S OWN SPEED when the transition starts (the owner's V3 list, anim stage F.1: the blend was always
-- started still, v0 = 0, so a clip cut mid-swing braked to a stop before it eased into the new one).
-- twist(q, n): the signed turn (radians, -pi..pi) a rotation q = (qx, qy, qz, qw) makes ABOUT the unit axis n - the
-- part of the joint's turn that runs along the offset's own axis (the rest of it is not what decays here)
function AnimLayers.twist(qx: number, qy: number, qz: number, qw: number, nx: number, ny: number, nz: number): number
	local along = qx * nx + qy * ny + qz * nz
	if math.abs(along) < 1e-12 and math.abs(qw) < 1e-12 then
		return 0 -- a half turn about an axis at right angles: none of it is along n
	end
	local a = 2 * math.atan2(along, qw)
	if a > math.pi then
		a -= 2 * math.pi
	elseif a < -math.pi then
		a += 2 * math.pi
	end
	return a
end

-- the offset's rate (per second) from its value now (x0) and a frame before (xPrev, dt seconds earlier); nil or a
-- frame too far back (a gap over maxGap, 0.1 s) is no speed (0); a jump past maxRate (radians a second, 60: about
-- 3,400 degrees a second, just over the fastest loved torso turn, 3,300) is a teleport, not a speed: held to that bar
function AnimLayers.offsetRate(x0: number, xPrev: number?, dt: number?, maxGap: number?, maxRate: number?): number
	if xPrev == nil or dt == nil or dt <= 1e-4 or dt > (maxGap or 0.1) then
		return 0
	end
	local d = x0 - xPrev
	if d > math.pi then -- (two readings either side of the half turn)
		d -= 2 * math.pi
	elseif d < -math.pi then
		d += 2 * math.pi
	end
	local cap = maxRate or 60
	return math.clamp(d / dt, -cap, cap)
end

-- ---------------------------------------------------------------- C5 motion warping
export type Warp = { from: number, to: number, scale: number, turn: number }

local function smooth(u: number): number
	u = math.clamp(u, 0, 1)
	return u * u * (3 - 2 * u)
end

local function rootSample(root: { { number } }, fps: number, t: number): (number, number, number)
	local n = #root
	if n == 0 then
		return 0, 0, 0
	end
	local f = math.clamp(t * fps, 0, n - 1)
	local i = math.floor(f)
	local j = math.min(n - 1, i + 1)
	local w = f - i
	local a, b = root[i + 1], root[j + 1]
	return a[1] + (b[1] - a[1]) * w, a[2] + (b[2] - a[2]) * w, (a[3] or 0) + ((b[3] or 0) - (a[3] or 0)) * w
end

AnimLayers.rootSample = rootSample

-- the root ("x z yaw" rows, character space, -Z forward) at t with the warp window's travel scaled and turned
function AnimLayers.warpedRootAt(root: { { number } }, fps: number, t: number, w: Warp?): (number, number, number)
	local x, z, yaw = rootSample(root, fps, t)
	if not w or t < w.from then
		-- (before the window the clip's own travel stands: the warp has not begun - it used to return the window's
		-- START here, so a window that opens late pulled the body ahead from the first frame; found by the spec 2026-11-14)
		return x, z, yaw
	end
	local x0, z0 = rootSample(root, fps, w.from)
	local te = math.clamp(t, w.from, math.max(w.from, w.to)) -- (a window written backwards has no length: no throw)
	local xe, ze = rootSample(root, fps, te)
	-- inside the window: the travel since its start, scaled and turned by the progress so far
	local u = if w.to > w.from then smooth((te - w.from) / (w.to - w.from)) else 1
	local turn = w.turn * u
	local dx, dz = (xe - x0) * w.scale, (ze - z0) * w.scale
	local c, s = math.cos(turn), math.sin(turn)
	local wx, wz = x0 + dx * c + dz * s, z0 - dx * s + dz * c
	if t > w.to then
		-- after the window: the clip's own remaining travel, turned by the full turn, from where the warp left it
		local rx, rz = x - xe, z - ze
		wx, wz = wx + rx * c + rz * s, wz - rx * s + rz * c
	end
	return wx, wz, yaw + turn
end

-- the scale and turn that bring the clip's travel in its window onto a target `dist` studs away at `angle` radians
-- (+ = to the left), stopping `contact` short of it; clamped so a warp never reads as sliding
function AnimLayers.warpFor(
	travel: number,
	dist: number,
	angle: number,
	contact: number?,
	limits: any?
): (number, number)
	local lim = limits or {}
	local minS, maxS = lim.minScale or 0.5, lim.maxScale or 1.6
	local maxTurn = math.rad(lim.maxTurnDeg or 35)
	local want = math.max(0, dist - (contact or 3))
	local scale = if travel > 1e-3 then math.clamp(want / travel, minS, maxS) else 1
	return scale, math.clamp(angle, -maxTurn, maxTurn)
end

-- ---------------------------------------------------------------- C4 reaction side
-- `attackerPos` and the victim's position / look (x, z); the side of the VICTIM the blow came from
function AnimLayers.reactionSide(ax: number, az: number, vx: number, vz: number, lookX: number, lookZ: number): string
	local dx, dz = ax - vx, az - vz
	local n = math.sqrt(dx * dx + dz * dz)
	if n < 1e-6 then
		return "Front"
	end
	dx, dz = dx / n, dz / n
	local fwd = dx * lookX + dz * lookZ -- toward the attacker along the victim's look
	local right = dx * -lookZ + dz * lookX -- the victim's right = look turned -90 about Y
	if math.abs(fwd) >= math.abs(right) then
		return if fwd >= 0 then "Front" else "Back"
	end
	return if right >= 0 then "Right" else "Left"
end

-- the REACTION MATRIX (AAA gaps v2 C3): the most specific reaction clip that exists for this hit - in the air
-- <base>Air, else <base><Side><Tier> (KatanaHitFrontHeavy), <base><Side>, <base><Tier>, <base>. `has(name)` says
-- whether a clip exists, so a set grows from one reaction to the whole matrix without touching a move
function AnimLayers.reactionName(
	base: string,
	side: string,
	tier: string?,
	airborne: boolean?,
	has: (string) -> boolean
): string
	local t = if type(tier) == "string" and #tier > 0
		then string.upper(string.sub(tier, 1, 1)) .. string.sub(tier, 2)
		else nil
	local order = {}
	if airborne then
		table.insert(order, base .. "Air")
	end
	if t then
		table.insert(order, base .. side .. t)
	end
	table.insert(order, base .. side)
	if t then
		table.insert(order, base .. t)
	end
	for _, name in order do
		if has(name) then
			return name
		end
	end
	return base
end

-- ---------------------------------------------------------------- C6 tracking
-- degrees per second the character may turn in a phase; `track` = { startup?, active?, recovery? } (missing = free)
function AnimLayers.turnAllowed(phase: string, track: any?): number
	if type(track) ~= "table" then
		return math.huge
	end
	local v = track[phase]
	if type(v) ~= "number" then
		return if phase == "active" then 0 else math.huge
	end
	return v
end

-- ---------------------------------------------------------------- D9 camera kick
-- the kick's size t seconds after the blow: the full `amp` at once, then a critically damped return
function AnimLayers.kick(t: number, amp: number, halflife: number?): number
	if t < 0 then
		return 0
	end
	local h = halflife or 0.03 -- a hit kick is back within ~0.2 s (0.06 left 14 % at 0.3 s)
	local k = math.log(2) / h
	return amp * (1 + k * t) * math.exp(-k * t)
end

-- ---------------------------------------------------------------- D5 look-at
-- the head's yaw / pitch (radians) toward a target at local (x, y, z) in the character's frame (-Z forward), clamped
-- so the head never turns past what a neck can (maxYaw / maxPitch degrees)
function AnimLayers.lookAngles(
	x: number,
	y: number,
	z: number,
	maxYawDeg: number?,
	maxPitchDeg: number?
): (number, number)
	local yaw = math.atan2(-x, -z)
	local flat = math.sqrt(x * x + z * z)
	local pitch = math.atan2(y, math.max(flat, 1e-6))
	local my, mp = math.rad(maxYawDeg or 70), math.rad(maxPitchDeg or 35)
	return math.clamp(yaw, -my, my), math.clamp(pitch, -mp, mp)
end

-- ATTENTION BEYOND THE HEAD (the owner's older list, AN-30: "look-at is narrower than coordinated attention ...
-- torso / weapon coordination and authored priority when the action permits it").
-- the way to a target at local (x, y, z) in the body's frame (-Z forward), NOT clamped: yaw + = to the left, radians
function AnimLayers.lookRaw(x: number, y: number, z: number): (number, number)
	local flat = math.sqrt(x * x + z * z)
	-- (straight overhead or underfoot there is no way round to turn: ahead - atan2(-0, -0) said "behind", and the
	-- look let go of a target passing over the head)
	local yaw = if flat < 1e-3 then 0 else math.atan2(-x, -z)
	return yaw, math.atan2(y, math.max(flat, 1e-6))
end

-- THE BARREL'S AIM (LIMITATIONS_FIXES_V4 4.4 / 13.4.3: idle barrel pitch / yaw in Anim.lookAt): a held gun at rest
-- is turned at its shoulder so its barrel follows the look. (bx, by, bz) = the barrel's way as the clip holds it,
-- (tx, ty, tz) = from the muzzle to the target, both in the torso's frame (-Z ahead, +Y up). -> yaw, pitch (radians)
-- to turn the shoulder by, in the torso's frame: the target's yaw and pitch less the barrel's, each the short way
-- round and clamped to maxYaw / maxPitch degrees (an arm turned further reads broken - a target behind is not aimed
-- at past that); nothing at all for a target behind by more than maxYaw + LOOK_GIVE (AnimLayers.lookWeight)
function AnimLayers.barrelTurn(
	bx: number,
	by: number,
	bz: number,
	tx: number,
	ty: number,
	tz: number,
	maxYaw: number?,
	maxPitch: number?
): (number, number)
	for _, v in { bx, by, bz, tx, ty, tz } do
		if v ~= v or math.abs(v) == math.huge then
			return 0, 0
		end
	end
	local yb, pb = AnimLayers.lookRaw(bx, by, bz)
	local yt, pt = AnimLayers.lookRaw(tx, ty, tz)
	local yaw = math.atan2(math.sin(yt - yb), math.cos(yt - yb))
	local pitch = pt - pb
	local my, mp = math.rad(maxYaw or 35), math.rad(maxPitch or 40)
	local w = AnimLayers.lookWeight(yaw, math.deg(my))
	return math.clamp(yaw, -my, my) * w, math.clamp(pitch, -mp, mp) * w
end

AnimLayers.LOOK_GIVE = 25 -- degrees past what head and body reach over which the look fades out

-- HOW MUCH of the look a target gets by where it is: all of it inside what head and body can reach together, none
-- from LOOK_GIVE degrees past that (a target behind the body is not craned at - and one that passes straight behind
-- does not throw the head from one shoulder to the other: clamped alone, the head snapped 140 degrees there).
function AnimLayers.lookWeight(yaw: number, reachDeg: number, giveDeg: number?): number
	local over = math.deg(math.abs(yaw)) - reachDeg
	local give = giveDeg or AnimLayers.LOOK_GIVE
	if not (over > 0) then
		return 1
	end
	local u = math.clamp(over / math.max(give, 1e-6), 0, 1)
	return 1 - u * u * (3 - 2 * u)
end

-- THE TURN SPLIT between the body and the head. yaw, pitch: the way to the target from the body's own facing
-- (lookRaw); bodyShare: the share of the yaw the body takes (0 = the head alone); maxBody / maxYaw / maxPitch:
-- degrees. Returns bodyYaw, headYaw, headPitch (radians): the body leads with its share up to its limit, the head
-- takes what is left up to a neck's, and both are scaled by lookWeight (a target behind gets neither).
-- R6 HAS NO WAIST: "the body" is the whole torso turned on its RootJoint (the caller turns the hips back so the legs
-- stay under it) - a spine's twist is not there to give.
-- The body takes its share OR what the head cannot reach, whichever is more (a small share with the head pinned at
-- its limit was the shoulder-pinned look again), so head and body together reach maxBody + maxYaw for any share.
-- twist: how far the CLIP has already turned the torso from the body's facing (radians): the head turns that much
-- less - the look is laid over the clip's own twist, it does not take it back.
function AnimLayers.lookSplit(
	yaw: number,
	pitch: number,
	bodyShare: number?,
	maxBodyDeg: number?,
	maxYawDeg: number?,
	maxPitchDeg: number?,
	twist: number?
): (number, number, number)
	if yaw ~= yaw or pitch ~= pitch then
		return 0, 0, 0
	end
	local function limit(deg: number?, own: number): number
		return math.rad(if deg and deg == deg then math.abs(deg) else own)
	end
	local share = if bodyShare and bodyShare == bodyShare then math.clamp(bodyShare, 0, 1) else 0
	local mb = if share > 0 then limit(maxBodyDeg, 20) else 0
	local my, mp = limit(maxYawDeg, 70), limit(maxPitchDeg, 35)
	local w = AnimLayers.lookWeight(yaw, math.deg(mb + my))
	local side = if yaw < 0 then -1 else 1
	local body = if share > 0 then side * math.min(math.max(math.abs(yaw) * share, math.abs(yaw) - my), mb) else 0
	local turned = if twist and twist == twist then twist else 0
	local head = math.clamp(yaw - turned - body, -my, my)
	return body * w, head * w, math.clamp(pitch, -mp, mp) * w
end

-- THE LEG KEPT WHERE IT STANDS while a layer turns the torso on its RootJoint. rootC0 / rootC1: the RootJoint's;
-- rootWas / rootNow: its Transform before and after the layer's turn; hipC0: the hip's. Returns what to put in
-- FRONT of the hip's own Transform. Exact whatever the clip (or another layer) has done to the torso - a lean, a
-- drop, a twist: worked out from "the torso as it was" against "the torso as it now is", not from the turn alone
-- (undone about the torso's own up, a torso the clip had pitched 30 degrees carried its feet half a stud).
function AnimLayers.keepLeg(rootC0: CFrame, rootC1: CFrame, rootWas: CFrame, rootNow: CFrame, hipC0: CFrame): CFrame
	local was = rootC0 * rootWas * rootC1:Inverse()
	local now = rootC0 * rootNow * rootC1:Inverse()
	return hipC0:Inverse() * (now:Inverse() * was) * hipC0
end

-- MAY THE BODY LOOK NOW? 1 when it may, 0 when the action does not permit it: a move that has COMMITTED (src/kit/
-- Moves takes the Humanoid's AutoRotate away for the active frames of a move that says `track`: the body may not
-- turn - neither may its head and torso swing after a target, the weapon's line and the pose are the move's), a
-- ragdoll, a seat. NOT every game means "committed" by AutoRotate off (a lock-on camera turns it off for good):
-- such a game passes its own `permit` to Anim.lookAt.
function AnimLayers.lookPermit(autoRotate: boolean, platformStand: boolean, sit: boolean): number
	return if autoRotate and not platformStand and not sit then 1 else 0
end

-- WHAT TO ATTEND TO: of several things a body could look at, the one with the highest priority; of equals, the one
-- named last (since: a number that grows with each naming). list: { [key] = { priority, since } }. nil when empty.
function AnimLayers.attention(list: { [string]: { priority: number, since: number } }): string?
	local best: string? = nil
	local bp, bs = -math.huge, -math.huge
	for key, a in list do
		local p, since = a.priority, a.since
		if
			p == p
			and since == since
			and (p > bp or (p == bp and since > bs) or (p == bp and since == bs and best ~= nil and key < best))
		then
			best, bp, bs = key, p, since
		end
	end
	return best
end

-- ---------------------------------------------------------------- D7 secondary motion
export type Swing = { x: number, v: number }

-- WHICH SIDE of an accessory's weld is the body's (Part1 = Part0 * C0 * C1^-1): "C0" when the body is Part0 and the
-- handle Part1 (a hat welded under the Head), "C1" when the handle is Part0 and the body Part1 (the engine's
-- "AccessoryWeld" under the Handle); nil when the weld does not hang a handle on the body. Pure.
function AnimLayers.weldSide(handle0: boolean, handle1: boolean, body0: boolean, body1: boolean): string?
	if body0 and handle1 then
		return "C0"
	elseif handle0 and body1 then
		return "C1"
	end
	return nil
end

-- ONE FRAME OF AN ACCESSORY'S SWAY (src/kit/AnimSecondary calls this for every accessory): the body's acceleration in
-- its own space (ax = to its right, az = backward: Roblox axes), dt seconds -> the two springs stepped and the tilt to
-- give the accessory, in radians: rx (forward / back, about X) and rz (side to side, about Z), each inside +-max.
-- A dt that is not a time, or a frame longer than a tenth of a second (a hitch), moves nothing: no kick on a stall.
export type SwayOptions = { stiffness: number?, damping: number?, gain: number?, max: number? }

function AnimLayers.sway(
	sx: Swing,
	sz: Swing,
	ax: number,
	az: number,
	dt: number,
	opts: SwayOptions?
): (Swing, Swing, number, number)
	local o: SwayOptions = opts or {}
	local maxRad = math.rad(if type(o.max) == "number" and o.max == o.max then math.max(o.max, 0) else 25)
	local nx, nz = sx, sz
	if dt == dt and dt > 0 and dt <= 0.1 and ax == ax and az == az then
		local gain = if type(o.gain) == "number" and o.gain == o.gain then o.gain else 0.02
		nx = AnimLayers.swing(sx, az * gain, dt, o.stiffness, o.damping)
		nz = AnimLayers.swing(sz, -ax * gain, dt, o.stiffness, o.damping)
	end
	return nx, nz, math.clamp(nx.x, -maxRad, maxRad), math.clamp(nz.x, -maxRad, maxRad)
end

-- one step of a damped spring pushed by an acceleration (an accessory lagging behind the body): stiffness k, damping
-- ratio z (0.4 = a little wobble)
function AnimLayers.swing(s: Swing, accel: number, dt: number, k: number?, z: number?): Swing
	-- (a spring stepped at 240 a second blows up past these: measured 2026-11-14 - stiffness 12,900 at damping 2)
	local K = if type(k) == "number" and k == k and k > 0 then math.min(k, 10000) else 60
	local Z = if type(z) == "number" and z == z and z >= 0 then math.min(z, 2) else 0.45
	local c = 2 * Z * math.sqrt(K)
	local steps = math.max(1, math.ceil(dt / (1 / 240)))
	local h = dt / steps
	local x, v = s.x, s.v
	for _ = 1, steps do
		local a = -K * x - c * v - accel
		v += a * h
		x += v * h
	end
	return { x = x, v = v }
end

-- WHAT KIND OF ACCESSORY IT IS decides how it moves (the owner's older list, AN-31: "rig-aware limits, collision
-- and quality tiers for hair, cloth, sheaths and flexible props"). One spring and one limit for everything let a
-- hat swing like a cape and a cape swing INTO the back. A class says the spring (stiffness, damping, gain) and
-- three limits in degrees: `away` (the hanging end swinging off the body), `into` (toward the body: small - the
-- stand-in for collision, see below) and `side`.
-- COLLISION, and why it is a limit: an accessory's Handle does not collide (CanCollide is off, and a worn mesh
-- has no shape the engine will sweep against the body each frame for a cosmetic), so "it does not pass through
-- the body" is kept the only way that costs nothing: the tilt is not allowed past a small angle on the body's
-- side. Which side that is follows from where the accessory hangs (below its attach point: hair, a cape, a
-- sheath) and, for a sheath, which hip it is on.
export type SwayClass = {
	stiffness: number,
	damping: number,
	gain: number,
	away: number,
	into: number,
	side: number,
	hip: boolean?, -- worn at the hip: its side limit is one-sided (it cannot swing into the leg)
}

local SWAY: { [string]: SwayClass } = {
	Hair = { stiffness = 50, damping = 0.45, gain = 0.02, away = 25, into = 4, side = 12 },
	Back = { stiffness = 35, damping = 0.4, gain = 0.025, away = 35, into = 2, side = 15 }, -- a cape, a pack, wings
	Waist = { stiffness = 60, damping = 0.5, gain = 0.02, away = 20, into = 20, side = 12, hip = true }, -- a sheath
	Hat = { stiffness = 90, damping = 0.6, gain = 0.01, away = 6, into = 6, side = 6 },
	Neck = { stiffness = 70, damping = 0.5, gain = 0.015, away = 10, into = 3, side = 6 }, -- a scarf, a necklace
	Shoulder = { stiffness = 80, damping = 0.55, gain = 0.01, away = 8, into = 3, side = 5 },
	Front = { stiffness = 80, damping = 0.55, gain = 0.01, away = 8, into = 2, side = 5 },
}
AnimLayers.SWAY_CLASSES = SWAY
-- an accessory that does not sway at all (it sits ON the face or the body: a tilt reads as a glitch)
local RIGID = {
	Face = true,
	Eyebrow = true,
	Eyelash = true,
	TShirt = true,
	Shirt = true,
	Pants = true,
	Jacket = true,
	Sweater = true,
	Shorts = true,
	LeftShoe = true,
	RightShoe = true,
	DressSkirt = true,
}

-- the class of an accessory by its AccessoryType's name -> the class; nil: it does not sway; "Unknown" (or a name
-- the kit has not met): the hat's - the smallest that still moves
function AnimLayers.swayClass(accessoryType: string?): SwayClass?
	if accessoryType and RIGID[accessoryType] then
		return nil
	end
	return SWAY[accessoryType or ""] or SWAY.Hat
end

-- the tilt held inside its class's limits: rx about X (+ = the hanging end goes FORWARD, into a body it hangs
-- behind), rz about Z (+ = the hanging end goes to the body's RIGHT). hipSide: +1 an accessory on the right hip,
-- -1 on the left, 0 neither. `max` (degrees): a game's own cap on every limit
function AnimLayers.swayLimit(
	rx: number,
	rz: number,
	class: SwayClass,
	hipSide: number?,
	max: number?,
	front: boolean?
): (number, number)
	local cap = if type(max) == "number" and max == max then math.max(max, 0) else math.huge
	local away, into, side =
		math.rad(math.min(class.away, cap)), math.rad(math.min(class.into, cap)), math.rad(math.min(class.side, cap))
	-- (front: the accessory hangs IN FRONT of the body - a necklace, a chest piece: the body is behind it, so the
	-- small side is the other one)
	local x = if rx ~= rx then 0 elseif front then math.clamp(rx, -into, away) else math.clamp(rx, -away, into)
	local z = if rz ~= rz then 0 else rz
	local s = hipSide or 0
	if class.hip and s ~= 0 then
		-- (the leg is on the body's side of a hip accessory: on the right hip the hanging end may not swing left)
		local inward = math.rad(math.min(3, cap))
		z = if s > 0 then math.clamp(z, -inward, side) else math.clamp(z, -side, inward)
	else
		z = math.clamp(z, -side, side)
	end
	return x, z
end

-- WHICH WAY IT TIPS: the spring's tilt is right for an accessory that STANDS UP from where it is worn (a hat: its
-- top lags behind the head). One that HANGS below its attach point (a cape, a sheath, long hair) pivots at its top:
-- the same tilt would swing its hanging end the way the body goes. Seen in Studio 2026-11-15: a cape went 2 degrees
-- FORWARD as the body sped up ahead. For a hanging accessory the tilt is turned round.
function AnimLayers.swayHang(rx: number, rz: number, hangs: boolean): (number, number)
	if hangs then
		return -rx, -rz
	end
	return rx, rz
end

-- A PUSH NO BODY GIVES: a teleport or a respawn reads as thousands of studs a second squared for one frame and
-- throws every spring to its limit. The acceleration is held to SWAY_PUSH (a hard stop from a sprint is about 60)
AnimLayers.SWAY_PUSH = 300
function AnimLayers.swayPush(ax: number, az: number, cap: number?): (number, number)
	if ax ~= ax or az ~= az or math.abs(ax) == math.huge or math.abs(az) == math.huge then
		return 0, 0 -- (a number that is none, or without end: no push - it would sit in the eased push for good)
	end
	local most = if type(cap) == "number" and cap == cap and cap > 0 then cap else AnimLayers.SWAY_PUSH
	local m = math.sqrt(ax * ax + az * az)
	if m > most then
		return ax / m * most, az / m * most
	end
	return ax, az
end

-- QUALITY TIERS by how far the camera is: every frame up close, every `SWAY_EVERY`th frame further off (the time
-- between is summed, so the spring moves as far), nothing beyond (the accessory goes back to how it is worn).
-- -> how many frames a step: 1, SWAY_EVERY, or 0 for off
AnimLayers.SWAY_NEAR = 40
AnimLayers.SWAY_FAR = 110
AnimLayers.SWAY_EVERY = 2
function AnimLayers.swayTier(distance: number?, near: number?, far: number?): number
	if not distance or distance ~= distance then
		return 1 -- (no camera to measure from - a server, a test: as if near)
	end
	if distance <= (near or AnimLayers.SWAY_NEAR) then
		return 1
	elseif distance <= (far or AnimLayers.SWAY_FAR) then
		return AnimLayers.SWAY_EVERY
	end
	return 0
end

-- ADDITIVE sampling (AAA gaps v2 D3): where `t` falls in a track's key `times` -> (i, j, f): rows i and j blended by f.
-- A looping track wraps (the last row blends back into the first); a one-shot holds its last row
function AnimLayers.sampleAt(times: { number }, t: number, loop: boolean?): (number, number, number)
	local n = #times
	if n <= 1 then
		return 1, 1, 0
	end
	local span = times[n] - times[1]
	if loop and span > 0 then
		t = times[1] + (t - times[1]) % span
	end
	if t <= times[1] then
		return 1, 1, 0
	elseif t >= times[n] then
		return n, n, 0
	end
	local lo, hi = 1, n
	while hi - lo > 1 do
		local mid = (lo + hi) // 2
		if times[mid] <= t then
			lo = mid
		else
			hi = mid
		end
	end
	local d = times[hi] - times[lo]
	return lo, hi, if d > 0 then (t - times[lo]) / d else 0
end

-- the weight of a layer `t` seconds in: up over `fadeIn`, down over the last `fadeOut` of `length` (smoothstep)
function AnimLayers.layerWeight(t: number, length: number, fadeIn: number, fadeOut: number): number
	local function ease(x: number): number
		x = math.clamp(x, 0, 1)
		return x * x * (3 - 2 * x)
	end
	local w = if fadeIn > 0 then ease(t / fadeIn) else 1
	if length < math.huge and fadeOut > 0 then
		w = math.min(w, ease((length - t) / fadeOut))
	end
	return w
end

-- an AUTHORED CAMERA TRACK (AAA gaps v2 D9): keys { t, loc = {x,y,z}, target = {x,y,z}, fov? } in the character's
-- starting root space (the cutscene camera's shape) -> where the camera is at `t`: eased (smoothstep) between keys,
-- held at both ends. Returns loc, target, fov (nil = leave the FOV alone)
function AnimLayers.cameraAt(keys: { any }, t: number): ({ number }, { number }, number?)
	local n = #keys
	local function lerp3(a: { number }, b: { number }, f: number): { number }
		return { a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, a[3] + (b[3] - a[3]) * f }
	end
	if n == 0 then
		return { 0, 0, 0 }, { 0, 0, -1 }, nil
	end
	local a, b = keys[1], keys[1]
	if t >= keys[n].t then
		a, b = keys[n], keys[n]
	elseif t > keys[1].t then
		for i = 1, n - 1 do
			if t >= keys[i].t and t <= keys[i + 1].t then
				a, b = keys[i], keys[i + 1]
				break
			end
		end
	end
	local span = b.t - a.t
	local f = if span > 0 then math.clamp((t - a.t) / span, 0, 1) else 0
	f = f * f * (3 - 2 * f)
	local fov: number? = nil
	if type(a.fov) == "number" then
		fov = if type(b.fov) == "number" then a.fov + (b.fov - a.fov) * f else a.fov
	end
	return lerp3(a.loc, b.loc, f), lerp3(a.target, b.target, f), fov
end

-- ---------------------------------------------------------------- several layers on one joint
-- ONE record a joint, shared by every runtime layer that writes it after the Animator (src/kit/Anim: look-at,
-- additive, feet). T is whatever the joint holds (a CFrame in the game, a number in the spec).
--   clean:   the value under the layers - the Animator's, or what the joint held before any layer touched it
--   written: what the layers left on the joint the last time one of them wrote
--   frame:   the frame a layer last asked for a base
--   users:   how many layers are on the joint
--   seen:    the layers that have asked this frame (a layer asking twice under one frame number is a new frame)
export type Stack<T> = { clean: T?, written: T?, frame: number?, users: number, seen: { [any]: boolean }? }

function AnimLayers.newStack(): Stack<any>
	return { users = 0 }
end

-- the ONE record of a joint, whoever asks (src/kit/Anim's layers, the blend when a clip starts, the get-up out of a
-- ragdoll in src/kit/AnimRagdoll): kept here so every writer of a joint shares it. Weak: it goes with the joint.
local records: { [any]: Stack<any> } = setmetatable({}, { __mode = "k" }) :: any
function AnimLayers.stackOf(joint: any): Stack<any>
	local stack = records[joint]
	if not stack then
		stack = AnimLayers.newStack()
		records[joint] = stack
	end
	return stack
end

-- the value UNDER the layers on a joint that holds `cur` now: the clean one when the joint still holds the layers'
-- write, else what it holds (a writer that wants "the pose the clip plays", outside its own frame)
function AnimLayers.stackClean<T>(stack: Stack<T>, cur: T, same: (T, T) -> boolean): T
	local clean, written = stack.clean, stack.written
	if clean ~= nil and written ~= nil and same(written, cur) then
		return clean
	end
	return cur
end

-- THE VALUE A LAYER BUILDS ON this frame. cur: what the joint holds now; frame: the same number for every layer in
-- one frame; same(a, b): are two values the same one (a read-back is never exactly the value written).
-- The first layer of a frame: if the joint still holds what the layers wrote last, nothing rewrote it - the clean
-- value under them; else the joint was rewritten (the Animator): that is the new clean value. Every later layer of
-- the same frame: what the layer before it wrote.
-- who (optional): the layer asking. A layer that asks AGAIN under the frame number it already asked under is in a
-- new frame whose number did not change (a clock that stood still): it is the first of that frame, not a later one
-- stacking on its own write - which would add its offset once more every such frame.
function AnimLayers.stackBase<T>(stack: Stack<T>, cur: T, frame: number, same: (T, T) -> boolean, who: any?): T
	local seen: { [any]: boolean } = stack.seen or {}
	if stack.frame == frame and not (who ~= nil and seen[who]) then
		if who ~= nil then
			seen[who] = true
			stack.seen = seen
		end
		return cur
	end
	stack.frame = frame
	stack.seen = if who ~= nil then { [who] = true } else nil
	local clean, written = stack.clean, stack.written
	if clean ~= nil and written ~= nil and same(written, cur) then
		return clean
	end
	stack.clean = cur
	return cur
end

function AnimLayers.stackWrite<T>(stack: Stack<T>, value: T)
	stack.written = value
end

-- A LAYER LEAVES. Returns the value to put back on the joint - its clean one - when this was the last layer on it
-- and the joint still holds the layers' write (no track drives it); nil otherwise (a track will rewrite it, or
-- another layer is still on it and will build on the clean value next frame by itself).
function AnimLayers.stackRelease<T>(stack: Stack<T>, cur: T, same: (T, T) -> boolean): T?
	stack.users = math.max(stack.users - 1, 0)
	if stack.users > 0 then
		return nil
	end
	local clean, written = stack.clean, stack.written
	stack.clean, stack.written, stack.frame, stack.seen = nil, nil, nil, nil
	if clean ~= nil and written ~= nil and same(written, cur) then
		return clean
	end
	return nil
end

return AnimLayers

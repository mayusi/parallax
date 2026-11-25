--!strict
-- AnimFeel (ReplicatedStorage.kit.AnimFeel) — the pure maths of WEIGHT layered on top of the clips at runtime, where
-- the craft puts it (board/plans/archive/2026-10-11-anim-research.md): a clip cannot know how fast the character is really
-- accelerating, the game can. No services, no instances; Anim.locomotion drives it, the kit's specs test it in Lune.
--
-- spring: Daniel Holden's critically damped spring by HALFLIFE ("Spring-It-On"): it reaches the goal without
--   overshoot, settling at a speed set by `halflife` (seconds), frame-rate independent (one step of dt = ten of dt/10).
-- lean: the body tilts INTO its acceleration and a little with its speed (Overgrowth's runtime lean: tilt =
--   velocity x k + acceleration x k, smoothed), so starting, stopping and turning read as weight shifting - the
--   same run clip looks heavier when the character pushes off and lighter when it coasts.
local AnimFeel = {}

local LN2 = 0.69314718056

export type Spring = { x: number, v: number }

-- one step of a critically damped spring toward `goal`; returns the new state
function AnimFeel.spring(s: Spring, goal: number, halflife: number, dt: number): Spring
	local y = (4 * LN2) / math.max(halflife, 1e-5) / 2 -- damping / 2 for a critically damped spring
	local j0 = s.x - goal
	local j1 = s.v + j0 * y
	local e = math.exp(-y * dt)
	return { x = e * (j0 + j1 * dt) + goal, v = e * (s.v - j1 * y * dt) }
end

export type LeanParams = {
	speedPitch: number?, -- radians of forward lean per stud/s of forward speed
	accelPitch: number?, -- radians per stud/s^2 of forward acceleration
	accelRoll: number?, -- radians per stud/s^2 of sideways acceleration (banking into a turn)
	maxPitch: number?,
	maxRoll: number?,
	halflife: number?, -- seconds: how quickly the body settles into the target lean
}
export type LeanState = { pitch: Spring, roll: Spring, lastVel: { x: number, z: number }? }

AnimFeel.LEAN_DEFAULTS = {
	speedPitch = 0.004,
	accelPitch = 0.012,
	accelRoll = 0.010,
	maxPitch = math.rad(14),
	maxRoll = math.rad(10),
	halflife = 0.12,
}

function AnimFeel.newLean(): LeanState
	return { pitch = { x = 0, v = 0 }, roll = { x = 0, v = 0 }, lastVel = nil }
end

local function clamp(v: number, m: number): number
	return math.max(-m, math.min(m, v))
end

-- velX / velZ: the character's ground velocity in its OWN space (x = right, z = forward is NEGATIVE: Roblox axes),
-- studs/s; dt seconds. Returns the new state and the lean angles (pitch + = forward, roll + = toward the right).
function AnimFeel.lean(
	state: LeanState,
	velX: number,
	velZ: number,
	dt: number,
	params: LeanParams?
): (LeanState, number, number)
	local p: LeanParams = params or ({} :: LeanParams)
	local d = AnimFeel.LEAN_DEFAULTS
	local speedPitch = p.speedPitch or d.speedPitch
	local accelPitch = p.accelPitch or d.accelPitch
	local accelRoll = p.accelRoll or d.accelRoll
	local maxPitch = p.maxPitch or d.maxPitch
	local maxRoll = p.maxRoll or d.maxRoll
	local halflife = p.halflife or d.halflife
	local last = state.lastVel or { x = velX, z = velZ }
	local dtc = math.max(dt, 1e-3)
	local accX, accZ = (velX - last.x) / dtc, (velZ - last.z) / dtc
	local forwardSpeed, forwardAccel = -velZ, -accZ
	local goalPitch = clamp(forwardSpeed * speedPitch + forwardAccel * accelPitch, maxPitch)
	local goalRoll = clamp(accX * accelRoll, maxRoll)
	local pitch = AnimFeel.spring(state.pitch, goalPitch, halflife, dt)
	local roll = AnimFeel.spring(state.roll, goalRoll, halflife, dt)
	return { pitch = pitch, roll = roll, lastVel = { x = velX, z = velZ } }, pitch.x, roll.x
end

-- ROOT MOTION (mission 04-anim 5.9): a one-shot with a `root` track (a lunge, a dash, a roll) MOVES the character -
-- 23 clips travel - but a KeyframeSequence only drives the Motor6Ds, so without this they played in place.
-- root: the clip's root frames { {qx, qy, qz, qw, px, py, pz} } (or the compact { {x, z, yaw} } Meta carries) in the
-- character's space at the clip's start; fps:
-- the clip's rate. Returns the offset at time t (clamped to the clip): x, y, z (studs) and yaw (radians, about +Y).
-- Pure: Anim applies it to the HumanoidRootPart (start CFrame * the offset), the specs test it in Lune.
function AnimFeel.rootAt(root: { { number } }, fps: number, t: number): (number, number, number, number)
	local n = #root
	if n == 0 then
		return 0, 0, 0, 0
	end
	local f = math.clamp(t * fps, 0, n - 1)
	local i = math.floor(f)
	local u = f - i
	local a, b = root[i + 1], root[math.min(i + 2, n)]
	if #a == 3 then -- the compact form { x, z, yaw } (Meta): the ground travel only
		local dy3 = (b[3] - a[3] + math.pi) % (2 * math.pi) - math.pi
		return a[1] + (b[1] - a[1]) * u, 0, a[2] + (b[2] - a[2]) * u, a[3] + dy3 * u
	end
	local function yaw(q: { number }): number
		return 2 * math.atan2(q[2], q[4]) -- a root turns about +Y only
	end
	local ya, yb = yaw(a), yaw(b)
	local dy = (yb - ya + math.pi) % (2 * math.pi) - math.pi -- the short way round
	return a[5] + (b[5] - a[5]) * u, a[6] + (b[6] - a[6]) * u, a[7] + (b[7] - a[7]) * u, ya + dy * u
end

return AnimFeel

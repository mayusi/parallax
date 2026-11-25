-- anim.luau — the kit's animation compiler (pure Luau, runs in Lune).
-- A spec (assets/animations/<Name>.json) or a Blender bake becomes ONE NEUTRAL CLIP, build/animations/<Name>.clip.json:
-- character-space transforms per joint (the authored keys with their easing when there are any, and dense frames
-- at the clip's fps always), events, beats, feel. The clip compiles to any rig's KeyframeSequence — R6, R15, a
-- custom rig read from the engine (kit/lib/animrig.luau) — and is what the strip, the motion metrics and the other
-- engines' exporters read.
--
-- Spec:
-- {
--   "name": "Slash", "loop": false, "priority": "Action", "fps": 30,
--   "keys": [
--     { "t": 0,    "ease": "Cubic", "dir": "Out", "pose": { "Right Arm": [0, 0, 0], "Torso": [0, 0, 0] } },
--     { "t": 0.15, "pose": { "Right Arm": [150, 0, 20], "Torso": [0, -25, 0] } },
--     { "t": 0.3,  "pose": { "Right Arm": [40, 0, -10], "Torso": [0, 30, 0] } }
--   ],
--   "events": [ { "t": 0.22, "name": "Hit" } ]          -- track:GetMarkerReachedSignal("Hit")
-- }
-- ROTATIONS ARE IN CHARACTER SPACE (degrees, CFrame.Angles order): X = right, Y = up, -Z = forward, applied at
-- the joint. "Right Arm": [90, 0, 0] points the arm forward; [0, 0, 90] raises it out to the right; "Left Arm"
-- [0, 0, -90] raises it to the left; "UpperTorso": [0, 30, 0] twists the upper body left (the waist — "Torso" is the
-- ROOT joint and turns the legs with it); "Head": [20, 0, 0] looks up (positive X lifts things forward/up — the same
-- rule that swings an arm forward). Verified on an R6 rig in Studio.
-- A pose may also be { "rot": [..], "pos": [..] } (pos = studs, character space). A joint keeps its last value
-- until a later key changes it (every keyframe lists every joint the clip moves, so interpolation is defined); a
-- key's ease/dir shape the motion FROM that key to the next.
-- ONLY joints a clip moves are controlled: the rest are written as Weight-0 containers (engine-verified: they do
-- not override other tracks), so an aim pose on the arms leaves the walk cycle on the legs alone.
-- BOTH RIGS from one spec: the R6 names above drive R15 too (Torso -> LowerTorso, Right Arm -> RightUpperArm, ...);
-- R15-only joints may be named as well (RightLowerArm, RightHand, UpperTorso, RightLowerLeg, RightFoot, ...). The clip
-- is kept in R15 joint names; the R6 version is a FOLD of it (Anim.foldToR6): Torso = LowerTorso then UpperTorso,
-- the upper limbs map, elbows / hands / knees / feet are dropped (an R6 limb is one piece), and a waist-only twist
-- counter-rotates the R6 legs and moves their hips back so the feet stay planted (which pins the R6 legs — R6 has
-- no waist). `kit anim` writes <Name> (R6) and <Name>_R15; Anim.play picks by RigType. A custom rig: "rig": "<name>".
local Rig = require("./animrig")

local CF, IDENTITY = Rig.CF, Rig.IDENTITY

local Anim = {}

-- the rig API (kit/lib/animrig.luau), re-exported
Anim.RIG_DIR = Rig.RIG_DIR
Anim.IDENTITY = Rig.IDENTITY
Anim.CF = Rig.CF
Anim.RIGS = Rig.RIGS
Anim.rig = Rig.rig
Anim.rigs = Rig.rigs
Anim.loadRigs = Rig.loadRigs
Anim.forgetRigs = Rig.forgetRigs
Anim.ingestRig = Rig.ingestRig
Anim.fk = Rig.fk
Anim.toJoint = Rig.toJoint
Anim.toJointM = Rig.toJointM
Anim.angles = Rig.angles
Anim.eulerOf = Rig.eulerOf
Anim.R15_FROM_R6 = Rig.R15_FROM_R6
Anim.R6_FROM_R15 = Rig.R6_FROM_R15

export type Issue = { path: string, message: string, severity: string }
export type Key = { t: number, rot: { number }, pos: { number }, ease: string, dir: string }
export type ClipJoint = { keys: { Key }?, frames: { { number } }? } -- frames: { qx, qy, qz, qw, px, py, pz } per time
export type Clip = {
	schema: number,
	name: string,
	rig: string, -- the joint namespace: "R15" (humanoids) or a custom rig's name
	fps: number,
	duration: number,
	loop: boolean,
	priority: string,
	joints: { [string]: ClipJoint },
	times: { number },
	events: { any },
	beats: any?,
	feel: any?,
	source: any?,
}

Anim.DEFAULT_FPS = 30
local EASE = { Linear = true, Constant = true, Elastic = true, Cubic = true, Bounce = true, CubicV2 = true }
local DIRS = { In = true, Out = true, InOut = true }
local PRIORITIES =
	{ Core = true, Idle = true, Movement = true, Action = true, Action2 = true, Action3 = true, Action4 = true }
local REST_ROT = { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 } }

-- What a Pose stores. PoseEasingStyle.Cubic is deprecated for CubicV2. PoseEasingDirection words mean what
-- TweenService's do — ENGINE-MEASURED 2026-10-10 (kit anim play: a CubicV2 "In" segment ran t^3, "Out" ran
-- 1-(1-t)^3, "InOut" both; docs that call them reversed are wrong) — so specs, clips and Poses share one convention:
-- In = slow start, Out = fast start.
local POSE_DIR = { In = "In", Out = "Out", InOut = "InOut" }
function Anim.poseStyle(style: string): string
	return if style == "Cubic" then "CubicV2" else style
end
function Anim.poseDirection(dir: string): string
	return POSE_DIR[dir] or "InOut"
end

-- ---------------------------------------------------------------- easing (Roblox's EasingStyle / EasingDirection)
local function bounceOut(t: number): number
	local n1, d1 = 7.5625, 2.75
	if t < 1 / d1 then
		return n1 * t * t
	elseif t < 2 / d1 then
		t -= 1.5 / d1
		return n1 * t * t + 0.75
	elseif t < 2.5 / d1 then
		t -= 2.25 / d1
		return n1 * t * t + 0.9375
	end
	t -= 2.625 / d1
	return n1 * t * t + 0.984375
end

local function easeIn(style: string, t: number): number
	if style == "Cubic" or style == "CubicV2" then
		return t * t * t
	elseif style == "Elastic" then
		if t <= 0 then
			return 0
		elseif t >= 1 then
			return 1
		end
		local p = 0.3
		return -(2 ^ (10 * (t - 1))) * math.sin((t - 1 - p / 4) * (2 * math.pi) / p)
	elseif style == "Bounce" then
		return 1 - bounceOut(1 - t)
	end
	return t -- Linear
end

-- the eased alpha (0..1) of style/dir at t (0..1)
function Anim.ease(style: string, dir: string, t: number): number
	t = math.clamp(t, 0, 1)
	if style == "Constant" then
		if dir == "In" then
			return if t >= 1 then 1 else 0
		elseif dir == "Out" then
			return if t > 0 then 1 else 0
		end
		return if t < 0.5 then 0 else 1
	end
	if dir == "In" then
		return easeIn(style, t)
	elseif dir == "Out" then
		return 1 - easeIn(style, 1 - t)
	end
	if t < 0.5 then
		return easeIn(style, 2 * t) / 2
	end
	return 1 - easeIn(style, 2 - 2 * t) / 2
end

-- ---------------------------------------------------------------- quaternions { x, y, z, w }
local Q = {}
Anim.Q = Q

-- ADDITIVE (AAA gaps v2 D3): a clip played ON TOP of any pose (a flinch over an attack, breathing over the guard) is
-- its change from a base frame: per moved joint and frame, delta = base^-1 * pose in the joint's own space (the
-- Motor6D.Transform space), so the runtime adds it as Transform * delta (src/kit/Anim.additive). `data` is
-- modelFromClip's second result; rows are "qx qy qz qw px py pz" strings (compact in Meta)
function Anim.additiveTrack(data: any, baseIndex: number?): { times: { number }, joints: { [string]: { string } } }
	local base = data.frames[math.clamp(math.floor((baseIndex or 0) + 1), 1, #data.frames)]
	-- at most 30 rows a second (the runtime blends between rows; 60 fps rows doubled Meta for nothing)
	local frames = {}
	for i, f in data.frames do
		local prev = frames[#frames]
		if not prev or i == #data.frames or f.t - prev.t >= 1 / 30 - 1e-6 then
			table.insert(frames, f)
		end
	end
	local out = { times = {}, joints = {} }
	for _, f in frames do
		table.insert(out.times, math.floor(f.t * 10000 + 0.5) / 10000)
	end
	for part, moved in data.moved do
		local b = base.transforms[part]
		if not moved or not b then
			continue
		end
		local bt = Rig.transpose3(b.rot)
		local rows = {}
		for _, f in frames do
			local tr = f.transforms[part]
			local m = Rig.mul3(bt, tr.rot)
			local dp = { tr.pos[1] - b.pos[1], tr.pos[2] - b.pos[2], tr.pos[3] - b.pos[3] }
			local p = {
				bt[1][1] * dp[1] + bt[1][2] * dp[2] + bt[1][3] * dp[3],
				bt[2][1] * dp[1] + bt[2][2] * dp[2] + bt[2][3] * dp[3],
				bt[3][1] * dp[1] + bt[3][2] * dp[2] + bt[3][3] * dp[3],
			}
			local q = Q.fromMatrix(m)
			table.insert(
				rows,
				string.format("%.4f %.4f %.4f %.4f %.3f %.3f %.3f", q[1], q[2], q[3], q[4], p[1], p[2], p[3])
			)
		end
		out.joints[part] = rows
	end
	return out
end

function Q.normalize(q: { number }): { number }
	local n = math.sqrt(q[1] * q[1] + q[2] * q[2] + q[3] * q[3] + q[4] * q[4])
	if n < 1e-12 then
		return { 0, 0, 0, 1 }
	end
	return { q[1] / n, q[2] / n, q[3] / n, q[4] / n }
end

function Q.fromMatrix(m: { { number } }): { number }
	local m11, m12, m13 = m[1][1], m[1][2], m[1][3]
	local m21, m22, m23 = m[2][1], m[2][2], m[2][3]
	local m31, m32, m33 = m[3][1], m[3][2], m[3][3]
	local tr = m11 + m22 + m33
	local x, y, z, w
	if tr > 0 then
		local s = math.sqrt(tr + 1) * 2
		w, x, y, z = 0.25 * s, (m32 - m23) / s, (m13 - m31) / s, (m21 - m12) / s
	elseif m11 > m22 and m11 > m33 then
		local s = math.sqrt(1 + m11 - m22 - m33) * 2
		w, x, y, z = (m32 - m23) / s, 0.25 * s, (m12 + m21) / s, (m13 + m31) / s
	elseif m22 > m33 then
		local s = math.sqrt(1 + m22 - m11 - m33) * 2
		w, x, y, z = (m13 - m31) / s, (m12 + m21) / s, 0.25 * s, (m23 + m32) / s
	else
		local s = math.sqrt(1 + m33 - m11 - m22) * 2
		w, x, y, z = (m21 - m12) / s, (m13 + m31) / s, (m23 + m32) / s, 0.25 * s
	end
	return Q.normalize({ x, y, z, w })
end

function Q.toMatrix(q: { number }): { { number } }
	local x, y, z, w = q[1], q[2], q[3], q[4]
	return {
		{ 1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w) },
		{ 2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w) },
		{ 2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y) },
	}
end

function Q.fromEuler(deg: { number }): { number }
	return Q.fromMatrix(Rig.angles(deg))
end

-- the shortest-path interpolation a -> b at t
function Q.slerp(a: { number }, b: { number }, t: number): { number }
	local dot = a[1] * b[1] + a[2] * b[2] + a[3] * b[3] + a[4] * b[4]
	if dot < 0 then
		b = { -b[1], -b[2], -b[3], -b[4] }
		dot = -dot
	end
	if dot > 0.9995 then
		return Q.normalize({
			a[1] + (b[1] - a[1]) * t,
			a[2] + (b[2] - a[2]) * t,
			a[3] + (b[3] - a[3]) * t,
			a[4] + (b[4] - a[4]) * t,
		})
	end
	local theta0 = math.acos(math.clamp(dot, -1, 1))
	local theta = theta0 * t
	local s0 = math.cos(theta) - dot * math.sin(theta) / math.sin(theta0)
	local s1 = math.sin(theta) / math.sin(theta0)
	return Q.normalize({ s0 * a[1] + s1 * b[1], s0 * a[2] + s1 * b[2], s0 * a[3] + s1 * b[3], s0 * a[4] + s1 * b[4] })
end

-- the angle between two rotations, degrees (4 atan2(|a - b|, |a + b|): exact near 0, where acos is not)
function Q.angle(a: { number }, b: { number }): number
	local dot = a[1] * b[1] + a[2] * b[2] + a[3] * b[3] + a[4] * b[4]
	local sgn = if dot < 0 then -1 else 1
	local dm, dp = 0, 0
	for i = 1, 4 do
		dm += (a[i] - sgn * b[i]) ^ 2
		dp += (a[i] + sgn * b[i]) ^ 2
	end
	return math.deg(4 * math.atan2(math.sqrt(dm), math.sqrt(dp)))
end

-- ---------------------------------------------------------------- spec -> clip
local function issuesOf(): ({ Issue }, (string, string) -> (), (string, string) -> ())
	local issues: { Issue } = {}
	return issues,
		function(path: string, message: string)
			table.insert(issues, { path = path, message = message, severity = "error" })
		end,
		function(path: string, message: string)
			table.insert(issues, { path = path, message = message, severity = "warn" })
		end
end

-- validate a spec and build its clip: joints in R15 names (R6 names mapped; a custom rig keeps its own), every joint
-- keyed at every spec key time (hold = its last value, rest before its first), dense frames sampled at fps.
function Anim.clipFromSpec(spec: any, opts: any?): (Clip?, { Issue })
	local issues, err, warn = issuesOf()
	local o = opts or {}
	if type(spec) ~= "table" or type(spec.name) ~= "string" or type(spec.keys) ~= "table" then
		err("spec", 'needs "name" and "keys": [ { "t": 0, "pose": { ... } }, ... ]')
		return nil, issues
	end
	local r6, r15 = Anim.RIGS.R6, Anim.RIGS.R15
	local space, custom = "R15", nil
	if spec.rig ~= nil and spec.rig ~= "R6" and spec.rig ~= "R15" and spec.rig ~= "both" then
		if type(spec.rig) == "string" and Anim.RIGS[spec.rig] and spec.rig ~= "R6" then
			space, custom = spec.rig, Anim.RIGS[spec.rig]
		else
			err(
				"rig",
				`rig must be "R6", "R15", "both" or a rig the kit read from the engine ({table.concat(
					Anim.rigs(),
					" | "
				)})`
			)
		end
	end
	local function resolve(part: string): string?
		if custom then
			return if custom.joints[part] then part else nil
		end
		if r15 and r15.joints[part] then
			return part
		end
		return Anim.R15_FROM_R6[part]
	end
	local function jointNames(): string
		if custom then
			return `{custom.rig}: {table.concat(custom.order, ", ")}`
		end
		local names = {}
		for _, rn in { r6, r15 } do
			if rn then
				table.insert(names, `{rn.rig}: {table.concat(rn.order, ", ")}`)
			end
		end
		return table.concat(names, "; ")
	end
	if spec.priority ~= nil and not PRIORITIES[spec.priority] then
		err("priority", "priority must be Core | Idle | Movement | Action | Action2 | Action3 | Action4")
	end
	local fps = o.fps or spec.fps or Anim.DEFAULT_FPS
	if type(fps) ~= "number" or fps < 1 or fps > 120 then
		err("fps", "fps must be a number from 1 to 120 (default 30)")
		fps = Anim.DEFAULT_FPS
	end
	if #spec.keys < 2 then
		err("keys", "an animation needs at least 2 keys (t = 0 and a later one)")
	end
	local joints: { [string]: ClipJoint } = {}
	local keyTimes: { { t: number, ease: string, dir: string } } = {}
	local last = -1
	for i, key in spec.keys do
		local path = `keys[{i}]`
		if type(key.t) ~= "number" or key.t <= last then
			err(path .. ".t", "key times must be numbers that strictly increase (first key t = 0)")
		end
		if i == 1 and key.t ~= 0 then
			err(path .. ".t", "the first key must be at t = 0")
		end
		last = if type(key.t) == "number" then key.t else last
		if key.ease ~= nil and not EASE[key.ease] then
			err(path .. ".ease", "ease must be Linear | Constant | Cubic | CubicV2 | Elastic | Bounce")
		end
		if key.dir ~= nil and not DIRS[key.dir] then
			err(path .. ".dir", "dir must be In | Out | InOut")
		end
		local ease, dir = key.ease or "Cubic", key.dir or "InOut"
		table.insert(keyTimes, { t = last, ease = ease, dir = dir })
		local direct = {} -- names of this rig space given directly in this key: they win over an R6 limb mapping to them
		for part in key.pose or {} do
			if (r15 and r15.joints[part]) or (custom and custom.joints[part]) then
				direct[part] = true
			end
		end
		for part, value in key.pose or {} do
			local joint = resolve(part)
			if not joint then
				err(`{path}.pose`, `"{part}" is not a joint ({jointNames()})`)
				continue
			end
			local rot = if type(value) == "table" and value.rot then value.rot else value
			local pos = if type(value) == "table" and value.pos then value.pos else { 0, 0, 0 }
			local okRot = type(rot) == "table" and #rot == 3
			for _, a in (if okRot then rot else {}) do
				if type(a) ~= "number" or math.abs(a) > 360 then
					okRot = false
				end
			end
			if not okRot then
				err(`{path}.pose.{part}`, "rotation must be [x, y, z] degrees within -360..360 (character space)")
				continue
			end
			local okPos = type(pos) == "table" and #pos == 3
			for _, d in (if okPos then pos else {}) do
				if type(d) ~= "number" or math.abs(d) > 10 then
					okPos = false
				end
			end
			if not okPos then
				err(`{path}.pose.{part}.pos`, "pos offsets must be [x, y, z] studs within ±10")
				continue
			end
			if joint ~= part and direct[joint] then
				continue
			end
			local j = joints[joint] or { keys = {} }
			joints[joint] = j
			table.insert(j.keys :: any, { t = last, rot = rot, pos = pos, ease = ease, dir = dir })
		end
	end
	if last > 30 then
		err("keys", `animation is {last}s long — keep clips ≤ 30 s`)
	end
	for i, ev in spec.events or {} do
		if type(ev.name) ~= "string" or not string.match(ev.name, "^[%w_]+$") then
			err(`events[{i}].name`, "event name must be letters/digits/_ (used with GetMarkerReachedSignal)")
		end
		if type(ev.t) ~= "number" or ev.t < 0 or ev.t > last then
			err(`events[{i}].t`, `event time must be within the clip (0..{last})`)
		end
	end
	-- every joint keyed at every spec key time: a hold of its last value (rest before its first key), with that
	-- key's easing — exactly what the engine sees when every keyframe lists every moved joint
	for _, j in joints do
		local full = {}
		local prev: Key? = nil
		local byTime = {}
		for _, k in j.keys :: any do
			byTime[k.t] = k
		end
		for _, kt in keyTimes do
			local k = byTime[kt.t]
			if not k then
				k = {
					t = kt.t,
					rot = if prev then table.clone(prev.rot) else { 0, 0, 0 },
					pos = if prev then table.clone(prev.pos) else { 0, 0, 0 },
					ease = kt.ease,
					dir = kt.dir,
				}
			end
			table.insert(full, k)
			prev = k
		end
		j.keys = full
	end
	if spec.loop then
		for name, j in joints do
			local a, b = (j.keys :: any)[1], (j.keys :: any)[#(j.keys :: any)]
			for k = 1, 3 do
				if math.abs(a.rot[k] - b.rot[k]) > 1 or math.abs(a.pos[k] - b.pos[k]) > 0.05 then
					warn("keys", `loop: last key differs from the first on "{name}" — the loop will pop`)
					break
				end
			end
		end
	end
	if next(joints) == nil and #issues == 0 then
		warn("keys", "no pose moves any joint — the animation does nothing")
	end
	local clip: Clip = {
		schema = 1,
		name = spec.name,
		rig = space,
		fps = fps,
		duration = math.max(last, 0),
		loop = spec.loop == true,
		priority = spec.priority or "Action",
		joints = joints,
		times = {},
		events = spec.events or {},
		beats = spec.beats,
		feel = spec.feel,
		source = o.source or { kind = "spec" },
	}
	-- (the tables the game enters it by: the build bakes them, kit/anim/match_tables.py `for`)
	(clip :: any).match = spec.match;
	-- (also built legs-free, for the game to play over the walk: kit/cmd/anim.luau AnimCmd.upperClip)
	(clip :: any).upper = spec.upper;
	-- (where its target stands and the contacts it means: kit/anim/contact.py, kit/anim/collide.py)
	(clip :: any).target = spec.target;
	(clip :: any).contact = spec.contact;
	-- (which hands hold the weapon: kit/anim/in_hand.py holds the clip to it. NOT "grip": that is the weapon's own
	-- joint track on a clip)
	(clip :: any).hands = spec.hands;
	-- (the slides a move means - a skid, a drag: kit/anim/foot_modes.py leaves that foot unjudged there)
	(clip :: any).slides = spec.slides;
	-- (the one finishing contract: the build applies it to every route's clip - kit/cmd/anim.luau AnimCmd.finish)
	(clip :: any).finish = spec.finish
	Anim.sample(clip)
	return clip, issues
end

-- the character-space value of a keyed joint at time t: (quaternion, pos)
local function keyedAt(keys: { Key }, qs: { { number } }, t: number): ({ number }, { number })
	if t <= keys[1].t then
		return qs[1], keys[1].pos
	end
	if t >= keys[#keys].t then
		return qs[#keys], keys[#keys].pos
	end
	for k = 1, #keys - 1 do
		local a, b = keys[k], keys[k + 1]
		if t >= a.t and t < b.t then
			local alpha = Anim.ease(a.ease, a.dir, (t - a.t) / (b.t - a.t))
			return Q.slerp(qs[k], qs[k + 1], alpha),
				{
					a.pos[1] + (b.pos[1] - a.pos[1]) * alpha,
					a.pos[2] + (b.pos[2] - a.pos[2]) * alpha,
					a.pos[3] + (b.pos[3] - a.pos[3]) * alpha,
				}
		end
	end
	return qs[#keys], keys[#keys].pos
end

-- dense frames at clip.fps for every keyed joint (clip.times: 0, 1/fps, ... and the exact end); a joint that only
-- has frames (a Blender bake) is left as it is
function Anim.sample(clip: Clip): Clip
	local fps = clip.fps or Anim.DEFAULT_FPS
	local n = math.floor(clip.duration * fps + 1e-6)
	local times = {}
	for i = 0, n do
		table.insert(times, i / fps)
	end
	if times[#times] < clip.duration - 1e-6 then
		table.insert(times, clip.duration)
	end
	clip.times = times
	for _, j in clip.joints do
		if j.keys and #j.keys > 0 then
			local keys = j.keys :: { Key }
			local qs = {}
			for k, key in keys do
				qs[k] = Q.fromEuler(key.rot)
			end
			local frames = {}
			for _, t in times do
				local q, p = keyedAt(keys, qs, t)
				table.insert(frames, { q[1], q[2], q[3], q[4], p[1], p[2], p[3] })
			end
			j.frames = frames
		end
	end
	return clip
end

-- the clip's value for one joint at a clip time (frame index i): rotation matrix + pos (character space)
function Anim.frameValue(j: ClipJoint, i: number): ({ { number } }, { number })
	local f = (j.frames :: any)[i]
	if not f then
		return REST_ROT, { 0, 0, 0 }
	end
	return Q.toMatrix({ f[1], f[2], f[3], f[4] }), { f[5], f[6], f[7] }
end

-- ---------------------------------------------------------------- R15 clip -> R6 clip
local function posOf(f: { number }): { number }
	return { f[5], f[6], f[7] }
end
local function mulV(m: { { number } }, v: { number }): { number }
	return {
		m[1][1] * v[1] + m[1][2] * v[2] + m[1][3] * v[3],
		m[2][1] * v[1] + m[2][2] * v[2] + m[2][3] * v[3],
		m[3][1] * v[1] + m[3][2] * v[2] + m[3][3] * v[3],
	}
end
local function packFrame(m: { { number } }, p: { number }): { number }
	local q = Q.fromMatrix(m)
	return { q[1], q[2], q[3], q[4], p[1], p[2], p[3] }
end

-- the rotation (3x3) that turns unit vector a onto unit vector b by the shortest arc
local function arcRotation(a: { number }, b: { number }): { { number } }
	local cx, cy, cz = a[2] * b[3] - a[3] * b[2], a[3] * b[1] - a[1] * b[3], a[1] * b[2] - a[2] * b[1]
	local d = a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
	local s2 = cx * cx + cy * cy + cz * cz
	if s2 < 1e-12 then
		if d > 0 then
			return { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 } }
		end
		-- opposite: half a turn about any axis perpendicular to a
		local ax = if math.abs(a[1]) < 0.9 then { 1, 0, 0 } else { 0, 1, 0 }
		local px, py, pz = a[2] * ax[3] - a[3] * ax[2], a[3] * ax[1] - a[1] * ax[3], a[1] * ax[2] - a[2] * ax[1]
		local n = math.sqrt(px * px + py * py + pz * pz)
		px, py, pz = px / n, py / n, pz / n
		return {
			{ 2 * px * px - 1, 2 * px * py, 2 * px * pz },
			{ 2 * py * px, 2 * py * py - 1, 2 * py * pz },
			{ 2 * pz * px, 2 * pz * py, 2 * pz * pz - 1 },
		}
	end
	local k = (1 - d) / s2
	return {
		{ 1 + k * (-cz * cz - cy * cy), k * cx * cy - cz, k * cx * cz + cy },
		{ k * cx * cy + cz, 1 + k * (-cz * cz - cx * cx), k * cy * cz - cx },
		{ k * cx * cz - cy, k * cy * cz + cx, 1 + k * (-cy * cy - cx * cx) },
	}
end

-- where an R15 two-piece limb's END pivot (wrist / ankle) is, relative to the limb's root pivot, in the parent
-- part's space, for character-space rotations of the upper and lower part (nil = rest)
local function limbEnd(
	rig: Rig,
	upper: string,
	lower: string,
	endJoint: string,
	rotUpper: { { number } }?,
	rotLower: { { number } }?
): { number }
	local ju, jl, je = rig.joints[upper], rig.joints[lower], rig.joints[endJoint]
	local tu = if rotUpper then CF.fromRot(rotUpper) else IDENTITY
	local tl = if rotLower then CF.fromRot(rotLower) else IDENTITY
	local upperCf = CF.mul(CF.mul(ju.c0, tu), CF.inv(ju.c1))
	local lowerCf = CF.mul(CF.mul(CF.mul(upperCf, jl.c0), tl), CF.inv(jl.c1))
	local endPivot = CF.mul(lowerCf, je.c0)
	return { endPivot[1] - ju.c0[1], endPivot[2] - ju.c0[2], endPivot[3] - ju.c0[3] }
end

local function unit(v: { number }): { number }
	local n = math.sqrt(v[1] * v[1] + v[2] * v[2] + v[3] * v[3])
	if n < 1e-9 then
		return { 0, -1, 0 }
	end
	return { v[1] / n, v[2] / n, v[3] / n }
end

-- an R6 limb (one piece) for an R15 two-piece limb: points from its pivot at the R15 wrist / ankle (shortest arc
-- from the rest direction); the R15 upper part's own position offset is kept
local R15_LIMBS = {
	["Right Arm"] = { "RightUpperArm", "RightLowerArm", "RightHand" },
	["Left Arm"] = { "LeftUpperArm", "LeftLowerArm", "LeftHand" },
	["Right Leg"] = { "RightUpperLeg", "RightLowerLeg", "RightFoot" },
	["Left Leg"] = { "LeftUpperLeg", "LeftLowerLeg", "LeftFoot" },
}
-- the one-piece limb's direction for an R15 end position e: arms point at the wrist (shortest arc from rest);
-- legs match the ankle's GROUND position with the R6 leg's own length (the foot lands where the R15 foot does)
local function limbDir(e: { number }, legLength: number?, standing: boolean?): { number }
	if not legLength then
		return unit(e)
	end
	local h = math.sqrt(e[1] * e[1] + e[3] * e[3])
	if standing then -- the foot lands where the R15 foot does
		if h >= legLength * 0.999 then
			return unit({ e[1], 0, e[3] })
		end
		return { e[1] / legLength, -math.sqrt(1 - (h / legLength) ^ 2), e[3] / legLength }
	end
	-- in the air: the foot clears as high as the R15 ankle does (a straight leg cannot fold)
	local dy = math.clamp(e[2] / legLength, -1, -0.05)
	local side = math.sqrt(1 - dy * dy)
	if h < 1e-6 then
		return { 0, dy, -side }
	end
	return { e[1] / h * side, dy, e[3] / h * side }
end

local function foldLimb(
	clip: Clip,
	r15: Rig,
	upper: string,
	lower: string,
	endJoint: string,
	legLength: number?,
	standing: { boolean }?
): ClipJoint?
	local ju, jl = clip.joints[upper], clip.joints[lower]
	if not ju and not jl then
		return nil
	end
	if not jl then
		return { keys = if ju.keys then table.clone(ju.keys) else nil, frames = ju.frames }
	end
	local restDir = unit(limbEnd(r15, upper, lower, endJoint))
	local out: ClipJoint = {}
	if (not ju or ju.keys) and jl.keys then
		local keys = {}
		local n = #(jl.keys :: any)
		for k = 1, n do
			local ku = if ju then (ju.keys :: any)[k] else nil
			local kl = (jl.keys :: any)[k]
			local e = limbEnd(r15, upper, lower, endJoint, if ku then Rig.angles(ku.rot) else nil, Rig.angles(kl.rot))
			local idx = nil
			for i, t in clip.times do
				if math.abs(t - kl.t) < 1e-6 then
					idx = i
				end
			end
			table.insert(keys, {
				t = kl.t,
				rot = Rig.eulerOf(arcRotation(restDir, limbDir(e, legLength, standing and idx and standing[idx]))),
				pos = if ku then table.clone(ku.pos) else { 0, 0, 0 },
				ease = kl.ease,
				dir = kl.dir,
			})
		end
		out.keys = keys
	end
	-- frames: the limb's turn is CARRIED from the frame before (the shortest arc from its last direction to this
	-- one), never rebuilt from rest - from rest, a hand raised over the head points opposite the rest, the arc's
	-- axis is undefined there and the arm spun up to 86 deg in one frame (a two-handed mocap combo, 2026-10-11)
	local frames = {}
	local prevDir, prevRot = nil, nil
	for i = 1, #clip.times do
		local mu = if ju then (Anim.frameValue(ju, i)) else nil
		local ml = Anim.frameValue(jl, i)
		local e = limbEnd(r15, upper, lower, endJoint, mu, ml)
		local pu = if ju then posOf((ju.frames :: any)[i]) else { 0, 0, 0 }
		local dir = limbDir(e, legLength, standing and standing[i])
		local rot
		if prevDir and prevRot then
			local a = arcRotation(prevDir, dir)
			rot = {}
			for r = 1, 3 do
				rot[r] = {}
				for c = 1, 3 do
					rot[r][c] = a[r][1] * prevRot[1][c] + a[r][2] * prevRot[2][c] + a[r][3] * prevRot[3][c]
				end
			end
		else
			rot = arcRotation(restDir, dir)
		end
		prevDir, prevRot = dir, rot
		table.insert(frames, { rot = rot, dir = dir, pos = pu } :: any)
	end
	-- a LOOP must close: carrying the turn lets the limb's roll drift around the cycle (a sprint's arm ended 10 deg
	-- off its first frame); the last frame points where the first does, so the gap is a roll about that direction -
	-- spread back over the cycle, a growing share each frame, about each frame's own direction
	local nf = #frames
	if clip.loop and nf > 2 then
		local first, last = (frames[1] :: any).rot, (frames[nf] :: any).rot
		local gap = {}
		for r = 1, 3 do
			gap[r] = {}
			for c = 1, 3 do
				gap[r][c] = first[r][1] * last[c][1] + first[r][2] * last[c][2] + first[r][3] * last[c][3]
			end
		end
		local d = (frames[nf] :: any).dir
		local sx = gap[3][2] - gap[2][3]
		local sy = gap[1][3] - gap[3][1]
		local sz = gap[2][1] - gap[1][2]
		local roll = math.atan2((sx * d[1] + sy * d[2] + sz * d[3]) / 2, (gap[1][1] + gap[2][2] + gap[3][3] - 1) / 2)
		for i = 1, nf do
			local f = frames[i] :: any
			local a = roll * (i - 1) / (nf - 1)
			local u = f.dir
			local cs, sn = math.cos(a), math.sin(a)
			local t = 1 - cs
			local R = {
				{ t * u[1] * u[1] + cs, t * u[1] * u[2] - sn * u[3], t * u[1] * u[3] + sn * u[2] },
				{ t * u[1] * u[2] + sn * u[3], t * u[2] * u[2] + cs, t * u[2] * u[3] - sn * u[1] },
				{ t * u[1] * u[3] - sn * u[2], t * u[2] * u[3] + sn * u[1], t * u[3] * u[3] + cs },
			}
			local m = {}
			for r = 1, 3 do
				m[r] = {}
				for c = 1, 3 do
					m[r][c] = R[r][1] * f.rot[1][c] + R[r][2] * f.rot[2][c] + R[r][3] * f.rot[3][c]
				end
			end
			f.rot = m
		end
	end
	for i = 1, nf do
		local f = frames[i] :: any
		frames[i] = packFrame(f.rot, f.pos)
	end
	out.frames = frames
	return out
end

-- the R6 clip of an R15-named clip: Torso = LowerTorso then UpperTorso; Head likewise; each one-piece R6 limb copies
-- the R15 upper part, or — when the clip bends the elbow / knee — points at the R15 wrist / ankle (foldLimb). A waist-only twist (UpperTorso keyed, root
-- and legs not) turns the whole R6 torso, so each R6 leg gets the inverse turn AND its hip moved back where it
-- was (R^T h - h in the torso's frame: the feet stay planted; the legs are pinned — R6 has no waist). Keys (with
-- easing) and frames both fold.
local CROUCH = 0.35 -- studs the R15 pelvis may sit below a straight R6 leg before the R6 pelvis follows it

function Anim.foldToR6(clip: Clip): (Clip, { Issue })
	local issues, _, warn = issuesOf()
	local r6 = Anim.RIGS.R6
	assert(r6, "no R6 rig data")
	local out: Clip = {
		schema = clip.schema,
		name = clip.name,
		rig = "R6",
		fps = clip.fps,
		duration = clip.duration,
		loop = clip.loop,
		priority = clip.priority,
		joints = {},
		times = clip.times,
		events = clip.events,
		beats = clip.beats,
		feel = clip.feel,
		source = clip.source,
	}
	local o: any = out
	local c: any = clip
	-- (hit_inferred / target / contact: what the build's contact and pass-through gates read on the R6 clip)
	-- (finish / finished / finish_log: the one finishing contract, applied before the fold - kit/anim/finish.py)
	for _, k in
		{
			"gate",
			"locomotion",
			"root",
			"camera",
			"hit_inferred",
			"target",
			"contact",
			"hands",
			"slides",
			"finish",
			"finished",
			"finish_log",
		}
	do
		o[k] = c[k]
	end
	local function copyJoint(from: string, to: string)
		local j = clip.joints[from]
		if j then
			out.joints[to] = { keys = if j.keys then table.clone(j.keys) else nil, frames = j.frames }
		end
	end
	copyJoint("Head", "Head")
	local r15 = Anim.RIGS.R15
	local function r6LegLength(leg: string): number
		local j = r6.joints[leg] -- hip pivot (C1 in the leg's frame) to the leg's bottom face
		return j.c1[2] + r6.sizes[leg][2] / 2
	end
	-- the sole's centre from the hip pivot, in the leg's frame: an R6 hip pivot sits on the leg's top OUTER edge
	-- (C1 = (0.5, 1, 0)), half a stud off the leg's axis — a sideways lean moves the sole up or down by that
	local function r6Sole(leg: string): { number }
		local j = r6.joints[leg]
		return { -j.c1[1], -j.c1[2] - r6.sizes[leg][2] / 2, -j.c1[3] }
	end
	-- the lowest corner of a box part placed by a CFrame (12 numbers: position, then the rotation's rows)
	local function lowestOf(cf: { number }, size: { number }): number
		local low = math.huge
		for _, sx in { -1, 1 } do
			for _, sy in { -1, 1 } do
				for _, sz in { -1, 1 } do
					local x, y, z = sx * size[1] / 2, sy * size[2] / 2, sz * size[3] / 2
					low = math.min(low, cf[2] + cf[7] * x + cf[8] * y + cf[9] * z)
				end
			end
		end
		return low
	end
	-- the lowest corner itself (where a pitched foot touches)
	local function lowestCornerOf(cf: { number }, size: { number }): { number }
		local best, bestP = math.huge, { cf[1], cf[2], cf[3] }
		for _, sx in { -1, 1 } do
			for _, sy in { -1, 1 } do
				for _, sz in { -1, 1 } do
					local x, y, z = sx * size[1] / 2, sy * size[2] / 2, sz * size[3] / 2
					local p = {
						cf[1] + cf[4] * x + cf[5] * y + cf[6] * z,
						cf[2] + cf[7] * x + cf[8] * y + cf[9] * z,
						cf[3] + cf[10] * x + cf[11] * y + cf[12] * z,
					}
					if p[2] < best then
						best, bestP = p[2], p
					end
				end
			end
		end
		return bestP
	end
	-- which R15 foot stands on the R15 floor at each frame (forward kinematics of the R15 clip)
	local standing: { [string]: { boolean } } = { RightFoot = {}, LeftFoot = {} }
	local ankleOf: { [string]: { { number } } } = { RightFoot = {}, LeftFoot = {} }
	local hipAt: { [string]: { { number } } } = { RightFoot = {}, LeftFoot = {} }
	if r15 and clip.joints.RightFoot and clip.joints.LeftFoot then
		local floor15 = math.huge
		for _, f in { "RightFoot", "LeftFoot" } do
			floor15 = math.min(floor15, r15.rest[f][2] - r15.sizes[f][2] / 2)
		end
		for i = 1, #clip.times do
			local transforms = {}
			for name, j in clip.joints do
				if r15.joints[name] and j.frames then
					local m, pp = Anim.frameValue(j, i)
					local jt, jp = Rig.toJointM(r15.joints[name].c0, m, pp)
					transforms[name] = { rot = jt, pos = jp }
				end
			end
			local world = Rig.fk(r15, transforms)
			for _, f in { "RightFoot", "LeftFoot" } do
				-- the foot touches the floor with its lowest EDGE (a heel strike, a toe-off): that is standing
				local height = lowestOf(world[f], r15.sizes[f]) - floor15
				-- the ankle relative to the hip, in the character's frame (what the R6 leg's rest axis is measured in)
				local lower = if f == "RightFoot" then "RightLowerLeg" else "LeftLowerLeg"
				local upperLeg = if f == "RightFoot" then "RightUpperLeg" else "LeftUpperLeg"
				local ankle = CF.mul(world[lower], r15.joints[f].c0)
				local hip = CF.mul(world.LowerTorso, r15.joints[upperLeg].c0)
				local d = { ankle[1] - hip[1], ankle[2] - hip[2], ankle[3] - hip[3] }
				-- standing = touching AND bearing weight: the hip above the foot (the leg within ~70 degrees of
				-- vertical); a body lying on the floor touches it with its heels and stands on nothing
				local len = math.sqrt(d[1] * d[1] + d[2] * d[2] + d[3] * d[3])
				standing[f][i] = height < 0.02 and len > 1e-6 and d[2] < -0.35 * len
				-- a foot pitched onto its toes (a sprint, a lunge's push-off) touches the floor well ahead of its ankle:
				-- the R6 sole lands where the R15 foot TOUCHES, blended in by the pitch (a flat or rolling foot keeps
				-- the ankle, so a heel-toe roll does not throw the one-piece leg about)
				if standing[f][i] then
					local cf = world[f]
					local pitch = math.deg(math.acos(math.clamp(cf[8], -1, 1)))
					local w = math.clamp((pitch - 15) / 30, 0, 1)
					if w > 0 then
						local touch = lowestCornerOf(cf, r15.sizes[f])
						d[1] += w * (touch[1] - ankle[1])
						d[3] += w * (touch[3] - ankle[3])
					end
				end
				ankleOf[f][i] = d
				hipAt[f][i] = { hip[1], hip[2], hip[3] }
			end
		end
		-- a one-piece leg cannot roll heel to toe: over every run of standing frames its sole holds ONE ground point
		-- (the run's touch points fitted to a line moving at the clip's ground speed - zero in a one-shot), so the leg
		-- pivots about a plant instead of copying the R15 foot's roll, its touchdown lag or a source's slide
		local total = #clip.times
		local cycle = if clip.loop then total - 1 else total
		local v = { 0, 0 }
		local loco = (clip :: any).locomotion
		if type(loco) == "table" and type(loco.speed) == "number" and type(loco.direction) == "table" then
			local dx, dz = loco.direction[1] or 0, loco.direction[3] or 0
			local n = math.sqrt(dx * dx + dz * dz)
			if n > 1e-6 then
				v = { -loco.speed * dx / n, -loco.speed * dz / n }
			end
		end
		local period = if clip.loop then clip.times[total] - clip.times[1] else 0
		-- the ground point is held in the WORLD: in a locomotion loop the character frame slides over it at the
		-- ground speed; in a one-shot with a `root` track (a lunge, a roll) the root's own travel is taken out
		local root = (clip :: any).root
		local function shift(i: number, t: number): (number, number)
			if type(root) == "table" and type(root[i]) == "table" then
				return root[i][5] or 0, root[i][7] or 0
			end
			return -v[1] * t, -v[2] * t
		end
		for _, f in { "RightFoot", "LeftFoot" } do
			local seen = {}
			for s0 = 1, cycle do
				local before = if clip.loop
					then standing[f][((s0 - 2) % cycle) + 1]
					else (s0 > 1 and standing[f][s0 - 1])
				if standing[f][s0] and not seen[s0] and not (before and (clip.loop or s0 > 1)) then
					local span, k, wrapped = {}, s0, false
					while standing[f][k] and not seen[k] and #span < cycle do
						table.insert(span, { k, if wrapped then clip.times[k] + period else clip.times[k] })
						seen[k] = true
						if clip.loop then
							if k == cycle then
								wrapped = true
							end
							k = (k % cycle) + 1
						else
							k += 1
							if k > total then
								break
							end
						end
					end
					if #span >= 1 then
						local ax, az = 0, 0
						for _, e in span do
							local i, t = e[1], e[2]
							local sx, sz = shift(i, t)
							local px = hipAt[f][i][1] + ankleOf[f][i][1] + sx
							local pz = hipAt[f][i][3] + ankleOf[f][i][3] + sz
							ax += px
							az += pz
						end
						ax /= #span
						az /= #span
						for _, e in span do
							local i, t = e[1], e[2]
							local sx, sz = shift(i, t)
							ankleOf[f][i][1] = ax - sx - hipAt[f][i][1]
							ankleOf[f][i][3] = az - sz - hipAt[f][i][3]
						end
					end
				end
			end
			if clip.loop and standing[f][total] and ankleOf[f][1] then
				-- the last frame of a loop is its first again: the same pose over the same ground point
				ankleOf[f][total] = {
					hipAt[f][1][1] + ankleOf[f][1][1] - hipAt[f][total][1],
					ankleOf[f][total][2],
					hipAt[f][1][3] + ankleOf[f][1][3] - hipAt[f][total][3],
				}
			end
		end
	end
	for limb, parts in R15_LIMBS do
		local isLeg = string.find(limb, "Leg") ~= nil
		local folded = if r15
			then foldLimb(
				clip,
				r15,
				parts[1],
				parts[2],
				parts[3],
				if isLeg then r6LegLength(limb) else nil,
				if isLeg then standing[parts[3]] else nil
			)
			else nil
		if folded then
			out.joints[limb] = folded
		else
			copyJoint(parts[1], limb)
		end
	end
	local lower, upper = clip.joints.LowerTorso, clip.joints.UpperTorso
	local nFrames = #clip.times
	if lower or upper then
		local torso: ClipJoint = {}
		if (not lower or lower.keys) and (not upper or upper.keys) then
			local keys = {}
			local nKeys = #((lower or upper).keys :: any)
			for k = 1, nKeys do
				local kl = if lower then (lower.keys :: any)[k] else nil
				local ku = if upper then (upper.keys :: any)[k] else nil
				local base = kl or ku
				local m = Rig.angles(if kl then kl.rot else { 0, 0, 0 })
				if ku then
					m = Rig.mul3(m, Rig.angles(ku.rot))
				end
				local pl = if kl then kl.pos else { 0, 0, 0 }
				local pu = if ku then ku.pos else { 0, 0, 0 }
				table.insert(keys, {
					t = base.t,
					rot = Rig.eulerOf(m),
					pos = { pl[1] + pu[1], pl[2] + pu[2], pl[3] + pu[3] },
					ease = base.ease,
					dir = base.dir,
				})
			end
			torso.keys = keys
		end
		local frames = {}
		for i = 1, nFrames do
			local ml, pl = if lower then Anim.frameValue(lower, i) else REST_ROT, { 0, 0, 0 }
			if lower then
				pl = posOf((lower.frames :: any)[i])
			end
			local mu, pu = if upper then Anim.frameValue(upper, i) else REST_ROT, { 0, 0, 0 }
			if upper then
				pu = posOf((upper.frames :: any)[i])
			end
			table.insert(frames, packFrame(Rig.mul3(ml, mu), { pl[1] + pu[1], pl[2] + pu[2], pl[3] + pu[3] }))
		end
		torso.frames = frames
		out.joints.Torso = torso
	end
	-- the R6 torso turns as ONE piece (LowerTorso then UpperTorso) while the R15 legs hang from LowerTorso alone: every
	-- R6 leg is expressed in the frame before UpperTorso's turn (R_u^T in front) and its hip pulled back to where
	-- LowerTorso keeps it (R_u^T h - h in the torso's frame) — a waist twist, a lean, a bend all stay off the feet
	if upper then
		for _, leg in { "Right Leg", "Left Leg" } do
			local hip = r6.joints[leg].c0
			local h = { hip[1], hip[2], hip[3] }
			local lj: ClipJoint = out.joints[leg] or {}
			if not lj.frames and not lj.keys then
				lj.frames = {}
				for _ = 1, nFrames do
					table.insert(lj.frames :: any, { 0, 0, 0, 1, 0, 0, 0 })
				end
			end
			if upper.keys then
				local keys = {}
				for k, ku in upper.keys :: any do
					local base = if lj.keys then (lj.keys :: any)[k] else nil
					local rot = if base then base.rot else { 0, 0, 0 }
					local pos = if base then base.pos else { 0, 0, 0 }
					local muT = Rig.transpose3(Rig.angles(ku.rot))
					local mh = mulV(muT, h)
					table.insert(keys, {
						t = ku.t,
						rot = Rig.eulerOf(Rig.mul3(muT, Rig.angles(rot))),
						pos = { pos[1] + mh[1] - h[1], pos[2] + mh[2] - h[2], pos[3] + mh[3] - h[3] },
						ease = if base then base.ease else ku.ease,
						dir = if base then base.dir else ku.dir,
					})
				end
				lj.keys = keys
			else
				lj.keys = nil -- (a dense upper torso: the leg goes dense too)
			end
			local frames = {}
			for i = 1, nFrames do
				local m, pp = Anim.frameValue(lj, i)
				local muT = Rig.transpose3((Anim.frameValue(upper, i)))
				local mh = mulV(muT, h)
				table.insert(
					frames,
					packFrame(Rig.mul3(muT, m), { pp[1] + mh[1] - h[1], pp[2] + mh[2] - h[2], pp[3] + mh[3] - h[3] })
				)
			end
			lj.frames = frames
			out.joints[leg] = lj
		end
		if not clip.joints.RightUpperLeg and not clip.joints.LeftUpperLeg then
			warn(
				"rig",
				"R6: the waist turn takes the legs (an R6 torso is one piece): under this clip a lower-priority walk cannot move them"
			)
		end
	end
	-- a standing R6 leg is solved in the WORLD: its sole (half a stud inboard of the hip pivot) lands ON its span's
	-- anchor point - the leg's axis points from the hip pivot at the floor point, its length fixed - so the sole
	-- holds that point exactly (the hip's xz from the folded torso, the height from the re-grounding below)
	if r15 and out.joints.Torso and out.joints.Torso.frames and clip.joints.RightFoot and clip.joints.LeftFoot then
		local tframes = out.joints.Torso.frames :: { { number } }
		for _, leg in { "Right Leg", "Left Leg" } do
			local foot = if leg == "Right Leg" then "RightFoot" else "LeftFoot"
			local lj = out.joints[leg]
			if lj and lj.frames then
				local hip = r6.joints[leg].c0
				local sole = r6Sole(leg)
				local reach = math.sqrt(sole[1] * sole[1] + sole[2] * sole[2] + sole[3] * sole[3])
				local soleDir = unit(sole)
				for i = 1, #clip.times do
					if standing[foot][i] and ankleOf[foot][i] and hipAt[foot][i] then
						local tf = tframes[i]
						local rc = Q.toMatrix({ tf[1], tf[2], tf[3], tf[4] })
						local _, lp = Anim.frameValue(lj, i)
						local hipW = mulV(rc, { hip[1] + lp[1], hip[2] + lp[2], hip[3] + lp[3] })
						local tx = hipAt[foot][i][1] + ankleOf[foot][i][1] - (tf[5] + hipW[1])
						local tz = hipAt[foot][i][3] + ankleOf[foot][i][3] - (tf[7] + hipW[3])
						local h = math.sqrt(tx * tx + tz * tz)
						local u
						if h >= reach * 0.999 then
							u = { tx / h, 0, tz / h }
						else
							u = { tx / reach, -math.sqrt(1 - (h / reach) ^ 2), tz / reach }
						end
						local m = Rig.mul3(Rig.transpose3(rc), arcRotation(soleDir, u))
						local fr = lj.frames :: any
						fr[i] = packFrame(m, lp)
					end
				end
			end
		end
	end
	-- re-ground: whenever an R15 foot stands on the R15 floor, the R6 pelvis sits where the R6 leg (its own length,
	-- straight) puts that foot on the R6 floor — the fold of a bent-knee gait keeps its feet down. Two standing legs
	-- at different tilts: the pelvis follows the one that landed LAST (a heel strike plants; the trailing foot, about
	-- to leave, floats a little — a straight leg's heel-rise); legs that landed together: the one needing it HIGHER
	-- (nothing digs in)
	if
		r15
		and (out.joints["Right Leg"] or out.joints["Left Leg"])
		and clip.joints.RightFoot
		and clip.joints.LeftFoot
	then
		local torso: ClipJoint = out.joints.Torso or { frames = {} }
		out.joints.Torso = torso
		local tframes: { { number } } = torso.frames or {}
		local changed = false
		-- how long each foot has stood, per frame (a loop wraps): the youngest stance is the one that just landed
		local age: { [string]: { number } } = { RightFoot = {}, LeftFoot = {} }
		local total = #clip.times
		for _, foot in { "RightFoot", "LeftFoot" } do
			for pass = 1, 2 do
				for i = 1, total do
					local prev = if i > 1
						then age[foot][i - 1]
						else (if clip.loop and pass == 2 then age[foot][total - 1] else 0)
					age[foot][i] = if standing[foot][i] then (prev or 0) + 1 else 0
				end
			end
		end
		for i = 1, #clip.times do
			local highest: number? = nil
			local lead: string? = nil
			local bottoms: { [string]: number } = {}
			if standing.RightFoot[i] and standing.LeftFoot[i] and age.RightFoot[i] ~= age.LeftFoot[i] then
				lead = if age.RightFoot[i] < age.LeftFoot[i] then "Right Leg" else "Left Leg"
			end
			-- the R6 torso's own rotation this frame (the hips and legs hang from it)
			local tf = tframes[i]
			local rc = if tf then Q.toMatrix({ tf[1], tf[2], tf[3], tf[4] }) else REST_ROT
			for _, leg in { "Right Leg", "Left Leg" } do
				local foot = if leg == "Right Leg" then "RightFoot" else "LeftFoot"
				local lj = out.joints[leg]
				if standing[foot][i] and lj and lj.frames then
					local m, lp = Anim.frameValue(lj, i)
					local hip = r6.joints[leg].c0
					-- the hip pivot (with the leg's own offset) and the sole under it, both in the torso's world
					local hipW = mulV(rc, { hip[1] + lp[1], hip[2] + lp[2], hip[3] + lp[3] })
					local bottomR6 = hipW[2] + mulV(Rig.mul3(rc, m), r6Sole(leg))[2]
					local floor6 = r6.rest[leg][2] - r6.sizes[leg][2] / 2
					local pelvisY = floor6 - bottomR6
					bottoms[leg] = bottomR6
					if lead then
						if leg == lead then
							highest = pelvisY
						end
					elseif highest == nil or pelvisY > highest then
						highest = pelvisY
					end
				end
			end
			if highest then
				-- a crouch or a roll: the R15 pelvis sits far lower than a straight R6 leg allows - follow it down (the
				-- legs shorten into the torso below), or an R6 character could never crouch. Small compressions (a jog's
				-- mid-stance) stay on the straight leg: following them slides the sole
				local lt = clip.joints.LowerTorso
				local crouch = false
				if lt and lt.frames then
					local _, lp15 = Anim.frameValue(lt, i)
					if lp15[2] < highest - CROUCH then
						-- a crouch is not a stance for a straight leg: the pelvis follows the R15 pelvis exactly and the
						-- legs follow the hip->ankle lines like legs in the air (the pass below holds their soles just
						-- over the floor) - the R6 way to crouch is a leg tilted forward under a low body, not a leg
						-- pushed a stud up through the torso
						highest = lp15[2]
						crouch = true
						standing.RightFoot[i] = false
						standing.LeftFoot[i] = false
					end
				end
				local f = tframes[i] or { 0, 0, 0, 1, 0, 0, 0 }
				tframes[i] = { f[1], f[2], f[3], f[4], f[5], highest, f[7] }
				changed = true
				if crouch then
					continue
				end
				-- a standing leg the pelvis now sits too low for (the trailing leg of a double support, whose R15
				-- heel is up) slides UP into the torso by the deficit: its sole stays on the floor, nothing digs in
				for leg, bottom in bottoms do
					local floor6 = r6.rest[leg][2] - r6.sizes[leg][2] / 2
					local deficit = floor6 - (highest + bottom)
					if deficit > 1e-4 then
						local lj = out.joints[leg]
						local m, lp = Anim.frameValue(lj, i)
						local fr = lj.frames :: any
						-- the lift is a WORLD-vertical move: expressed in the (tilted) torso's frame the pos offset lives in
						local up = mulV(Rig.transpose3(rc), { 0, deficit, 0 })
						fr[i] = packFrame(m, { lp[1] + up[1], lp[2] + up[2], lp[3] + up[3] })
					end
				end
			end
		end
		if changed then
			for i = 1, #clip.times do
				tframes[i] = tframes[i] or { 0, 0, 0, 1, 0, 0, 0 }
			end
			torso.frames = tframes
			if torso.keys then
				local byTime = {}
				for i, t in clip.times do
					byTime[t] = i
				end
				for _, k in torso.keys :: any do
					local i = byTime[k.t]
					if i then
						k.pos = { k.pos[1], tframes[i][6], k.pos[3] }
					end
				end
			end
		end
	end
	-- in the air, each R6 leg follows the R15 hip->ankle line (the thigh and shin summed: continuous while a knee
	-- folds), under the re-grounded pelvis and the torso's real rotation; where that straight leg would put its sole
	-- through the R6 floor (a vertical leg under a pelvis the stance leg lowered) it slides UP into the torso by the
	-- deficit instead of tilting (the sole skims 0.08 over the floor) — the top of an R6 leg sits inside the torso, so
	-- nothing shows, and the leg never snaps from back to front to buy clearance
	if r15 and out.joints.Torso and out.joints.Torso.frames and clip.joints.RightFoot and clip.joints.LeftFoot then
		local tframes = out.joints.Torso.frames :: { { number } }
		for _, leg in { "Right Leg", "Left Leg" } do
			local foot = if leg == "Right Leg" then "RightFoot" else "LeftFoot"
			local lj = out.joints[leg]
			if lj and lj.frames then
				local hip = r6.joints[leg].c0
				local sole = r6Sole(leg)
				local floor6 = r6.rest[leg][2] - r6.sizes[leg][2] / 2
				for i = 1, #clip.times do
					if not standing[foot][i] and ankleOf[foot][i] then
						local tf = tframes[i]
						local rc = Q.toMatrix({ tf[1], tf[2], tf[3], tf[4] })
						local pelvisY = tf[6]
						local _, lp = Anim.frameValue(lj, i)
						local hipW = mulV(rc, { hip[1] + lp[1], hip[2] + lp[2], hip[3] + lp[3] })
						-- the R15 hip->ankle line, in the character's frame
						local dirW = unit(ankleOf[foot][i])
						if dirW[2] > -0.05 then
							dirW = unit({ dirW[1], -0.05, dirW[3] })
						end
						local arc = arcRotation({ 0, -1, 0 }, dirW) -- maps the leg's rest axis (down) onto that line
						local soleY = pelvisY + hipW[2] + mulV(arc, sole)[2] - floor6
						-- held clear of the gates' contact band (0.04): a world-vertical lift, in the torso's frame
						local up = mulV(Rig.transpose3(rc), { 0, math.max(0, 0.08 - soleY), 0 })
						-- the leg's rotation under the torso: rc * m = arc
						local m = Rig.mul3(Rig.transpose3(rc), arc)
						local fr = lj.frames :: any
						fr[i] = packFrame(m, { lp[1] + up[1], lp[2] + up[2], lp[3] + up[3] })
					end
				end
				if lj.keys then
					local byTime = {}
					for i, t in clip.times do
						byTime[t] = i
					end
					for _, k in lj.keys :: any do
						local i = byTime[k.t]
						if i then -- every key follows its frame (grounding and the slide both moved legs)
							local f = (lj.frames :: any)[i]
							k.rot = Rig.eulerOf(Q.toMatrix({ f[1], f[2], f[3], f[4] }))
							k.pos = { f[5], f[6], f[7] }
						end
					end
				end
			end
		end
	end
	return out, issues
end

-- ---------------------------------------------------------------- clip -> a rig's KeyframeSequence (Rojo model)
local function sortedTimes(set: { [number]: boolean }): { number }
	local out = {}
	for t in set do
		table.insert(out, t)
	end
	table.sort(out)
	return out
end

-- rigName: "R6" | "R15" | a custom rig. Returns (model, data, issues): data.frames = the keyframes written, each
-- { t, ease, dir, pose = { part = { rot = [x, y, z] deg, pos } } (character space), transforms = { part = { rot = 3x3,
-- pos } } (joint space, what the Pose holds) }.
function Anim.modelFromClip(clip: Clip, rigName: string): (any?, any, { Issue })
	local issues, err, warn = issuesOf()
	local rig = Anim.RIGS[rigName]
	if not rig then
		err("rig", `unknown target rig "{tostring(rigName)}" ({table.concat(Anim.rigs(), " | ")})`)
		return nil, nil, issues
	end
	if clip.rig ~= rigName then
		err(
			"rig",
			`clip "{clip.name}" is in {clip.rig} joint names — fold it first (Anim.foldToR6) to compile for {rigName}`
		)
		return nil, nil, issues
	end
	local sources: { [string]: { string } } = {}
	for name in clip.joints do
		if rig.joints[name] then
			sources[name] = { name }
		end
	end
	local moved: { [string]: boolean } = {}
	for part in sources do
		moved[part] = true
	end
	if next(moved) == nil then
		warn("keys", `no pose moves any {rigName} joint — this version of the animation does nothing`)
	end
	-- authored keys (with easing) when every clip joint has them; the dense frames otherwise
	local authored = true
	for _, j in clip.joints do
		if not j.keys then
			authored = false
		end
	end
	-- an object a clip carries on a joint of its own (kit/anim/handoff.py: clip.props) moves every frame: the dense
	-- frames, not the keys
	local carried = type((clip :: any).props) == "table" and next((clip :: any).props) ~= nil
	if carried then
		authored = false
	end
	local times: { number }
	if authored then
		local set = {}
		for _, j in clip.joints do
			for _, k in j.keys :: any do
				set[k.t] = true
			end
		end
		times = sortedTimes(set)
	else
		times = clip.times
	end
	if #times == 0 then
		times = { 0 }
	end
	local frameIndex = {}
	for i, t in clip.times do
		frameIndex[t] = i
	end
	-- one clip joint at a keyframe time -> (3x3 rot, pos, euler?, ease, dir)
	local function valueAt(name: string, t: number): ({ { number } }, { number }, { number }?, string, string)
		local j = clip.joints[name]
		if authored then
			local keys = j.keys :: { Key }
			local hit: Key? = nil
			for _, k in keys do
				if math.abs(k.t - t) < 1e-6 then
					hit = k
					break
				elseif k.t < t then
					hit = k
				end
			end
			if not hit then
				return REST_ROT, { 0, 0, 0 }, { 0, 0, 0 }, keys[1].ease, keys[1].dir
			end
			return Rig.angles(hit.rot), hit.pos, hit.rot, hit.ease, hit.dir
		end
		local i = frameIndex[t]
		local rot, pos = Anim.frameValue(j, i or 0)
		return rot, pos, nil, "Linear", "InOut"
	end
	local frames = {}
	for _, t in times do
		local pose, transforms = {}, {}
		local ease, dir = "Cubic", "InOut"
		for part, names in sources do
			local m, p = REST_ROT, { 0, 0, 0 }
			local euler: { number }? = nil
			for k, name in names do
				local rot, pos, eu, e, d = valueAt(name, t)
				if k == 1 then
					m, p, euler, ease, dir = rot, pos, eu, e, d
				else
					m = Rig.mul3(m, rot)
					p = { p[1] + pos[1], p[2] + pos[2], p[3] + pos[3] }
					euler = nil
				end
			end
			pose[part] = { rot = euler or Rig.eulerOf(m), pos = p }
			local jt, jp = Rig.toJointM(rig.joints[part].c0, m, p)
			transforms[part] = { rot = jt, pos = jp }
		end
		table.insert(frames, { t = t, ease = ease, dir = dir, pose = pose, transforms = transforms })
	end
	-- the Pose tree: KeyframeSequence > Keyframe > Pose (root) > Pose ... only moved joints and their parents
	local children: { [string]: { string } } = {}
	for _, part in rig.order do
		local parent = rig.joints[part].parent
		children[parent] = children[parent] or {}
		table.insert(children[parent], part)
	end
	-- (filled below, once the tracks are read: the objects carried on each part)
	local propsOn: { [string]: { { name: string, at: (number) -> { number } } } } = {}
	local function needed(part: string): boolean
		if moved[part] or propsOn[part] then
			return true
		end
		for _, c in children[part] or {} do
			if needed(c) then
				return true
			end
		end
		return false
	end
	-- the Handle track at a keyframe time: its own frame when the time is one of the clip's, else the nearest one
	local function trackAt(track: any): ((number) -> { number })?
		if rigName ~= "R6" or type(track) ~= "table" or #track ~= #clip.times or #track == 0 then
			return nil
		end
		return function(t: number): { number }
			local i = frameIndex[t]
			if not i then
				local best = math.huge
				for k, tk in clip.times do
					if math.abs(tk - t) < best then
						best, i = math.abs(tk - t), k
					end
				end
			end
			return track[i or 1]
		end
	end
	local handleAt = trackAt((clip :: any).grip)
	-- GRIP ORIGIN AT THE HAND (opt-in: a move's "grip_origin": "hand", copied to clip.sword): the clip's grip track
	-- has its origin at the two hands' MIDPOINT, so the right hand's joint carries a constant slide of half the hand
	-- spacing up the handle - and every fade toward a track that does not key the joint (an idle) lerps that slide
	-- while the turn is slerped: the hand left the handle by ~0.1 st (kit_integration_arena, 2026-11-22). Exported
	-- with its origin at the RIGHT hand the pose turns about the hand and carries ~no translation, so a fade never
	-- pulls the hand off the handle; the game's joint takes the half spacing in its C1 (src/kit/AnimGrip.luau
	-- handOffset, the contract's animSword gripOrigin). The clip json, and every tool that reads it, is unchanged
	local sw = (clip :: any).sword
	local handOff = if type(sw) == "table" and sw.grip_origin == "hand" then (tonumber(sw.grip) or 0) / 2 else 0
	-- the LEFT hand's weapon (kit/anim/grip.py grip_left: Sample Game's Onyx) - a "Handle" pose under the Left Arm
	local handleLeftAt = trackAt((clip :: any).grip_left)
	-- OBJECTS ON JOINTS OF THEIR OWN (kit/anim/handoff.py clip.props: a magazine, a coin): a Pose named as the object
	-- under its carrier's, its track already the joint-space Transform (src/kit/AnimProp.luau AnimProp.socket builds
	-- the Motor6D: Part0 = the carrier, C0 = the record's c0, C1 = identity)
	if carried then
		local names = {}
		for name in (clip :: any).props do
			table.insert(names, name)
		end
		table.sort(names)
		for _, name in names do
			local pr = (clip :: any).props[name]
			local at = if type(pr) == "table" then trackAt(pr.frames) else nil
			local carrier = if type(pr) == "table" then pr.carrier else nil
			if at and type(carrier) == "string" and (rig.joints[carrier] or carrier == rig.root) then
				propsOn[carrier] = propsOn[carrier] or {}
				table.insert(propsOn[carrier], { name = name, at = at })
			else
				warn("props", `the object "{name}" has no track of the clip's length on a part of {rigName}: left out`)
			end
		end
	end
	local function node(frame: any, part: string): any
		local props: { [string]: any } = { Weight = if moved[part] then 1 else 0 }
		if moved[part] then
			local tr = frame.transforms[part]
			props.CFrame = { CFrame = { position = tr.pos, orientation = tr.rot } }
			props.EasingStyle = Anim.poseStyle(frame.ease)
			props.EasingDirection = Anim.poseDirection(frame.dir)
		else
			props.CFrame = { CFrame = { position = { 0, 0, 0 }, orientation = REST_ROT } }
		end
		local kids = {}
		for _, c in children[part] or {} do
			if needed(c) then
				table.insert(kids, node(frame, c))
			end
		end
		-- the sword as its own joint (kit/anim/grip.py, board m39b): a clip with a `grip` track keys a Motor6D named
		-- "Handle" under the Right Arm (src/kit/AnimGrip.luau builds that joint in the game); the track already holds
		-- the joint-space Transform, so it is written as it is
		local handleFor = if part == "Right Arm" then handleAt elseif part == "Left Arm" then handleLeftAt else nil
		if moved[part] and handleFor then
			local g = handleFor(frame.t)
			local m = Q.toMatrix(g)
			local off = if part == "Right Arm" then handOff else 0
			local pos = { g[5] + off * m[1][2], g[6] + off * m[2][2], g[7] + off * m[3][2] }
			if off > 0 then
				-- (the right hand HOLDS the handle: only the slide along it is kept - an arm solve that falls a
				-- hundredth short of its target, Katana5's first frames at 0.018 st, no longer leaves it beside it)
				local along = m[1][2] * pos[1] + m[2][2] * pos[2] + m[3][2] * pos[3]
				pos = { along * m[1][2], along * m[2][2], along * m[3][2] }
			end
			table.insert(kids, {
				Name = "Handle",
				ClassName = "Pose",
				Properties = {
					Weight = 1,
					CFrame = {
						CFrame = {
							-- (Transform x T(0, off, 0): the weapon frame's origin moved up the handle to the hand)
							position = pos,
							orientation = m,
						},
					},
					EasingStyle = Anim.poseStyle("Linear"),
					EasingDirection = Anim.poseDirection("InOut"),
				},
			})
		end
		for _, pr in propsOn[part] or {} do
			local g = pr.at(frame.t)
			table.insert(kids, {
				Name = pr.name,
				ClassName = "Pose",
				Properties = {
					Weight = 1,
					CFrame = { CFrame = { position = { g[5], g[6], g[7] }, orientation = Q.toMatrix(g) } },
					EasingStyle = Anim.poseStyle("Linear"),
					EasingDirection = Anim.poseDirection("InOut"),
				},
			})
		end
		return { Name = part, ClassName = "Pose", Properties = props, Children = if #kids > 0 then kids else nil }
	end
	local keyframes = {}
	local marked = {}
	for _, frame in frames do
		local kids = { node(frame, rig.root) }
		for i, ev in clip.events do
			if type(ev.t) == "number" and math.abs(ev.t - frame.t) < 1e-6 then
				table.insert(
					kids,
					{ Name = ev.name, ClassName = "KeyframeMarker", Properties = { Value = tostring(ev.value or "") } }
				)
				marked[i] = true
			end
		end
		table.insert(
			keyframes,
			{ Name = "Keyframe", ClassName = "Keyframe", Properties = { Time = frame.t }, Children = kids }
		)
	end
	-- SWORD SUB-KEYS (hand-origin clips, the owner 2026-11-22: "Add the extra keys"): the engine lerps a Pose's
	-- position and slerps its turn, so a residual slide along the handle (Katana5's hand spacing varies 0.19..0.25)
	-- drifts OFF the handle between two keys the blade turns far across (44 deg: 0.017 st). Where the Handle turns
	-- more than SUB_TURN degrees between two frames, up to 3 keyframes holding ONLY the Handle pose are added between
	-- them, interpolated in the blade's own frame (the turn slerped, the slide lerped along the handle) - the parent
	-- Poses ride at Weight 0 (not keys: the body moves exactly as before), the drift falls with the square of the step
	local SUB_TURN = 12
	if handOff > 0 and handleAt and type((clip :: any).grip) == "table" then
		local g = (clip :: any).grip
		local chain = {} -- the Pose path from the root down to the Right Arm (the Handle's carrier)
		local at = "Right Arm"
		while at and at ~= rig.root do
			table.insert(chain, 1, at)
			at = rig.joints[at] and rig.joints[at].parent
		end
		local function exported(k: number): ({ number }, { number })
			local m = Q.toMatrix(g[k])
			local p = {
				g[k][5] + handOff * m[1][2],
				g[k][6] + handOff * m[2][2],
				g[k][7] + handOff * m[3][2],
			}
			-- the slide in the blade's own frame (m^T p), along the handle only - as the keys themselves are written
			return { g[k][1], g[k][2], g[k][3], g[k][4] }, { 0, m[1][2] * p[1] + m[2][2] * p[2] + m[3][2] * p[3], 0 }
		end
		for k = 1, #g - 1 do
			local q0, l0 = exported(k)
			local q1, l1 = exported(k + 1)
			local turn = Q.angle(q0, q1)
			if turn > SUB_TURN then
				local count = math.min(3, math.ceil(turn / SUB_TURN) - 1)
				local t0, t1 = clip.times[k], clip.times[k + 1]
				for j = 1, count do
					local u = j / (count + 1)
					local q = Q.slerp(q0, q1, u)
					local m = Q.toMatrix(q)
					local l = { l0[1] + (l1[1] - l0[1]) * u, l0[2] + (l1[2] - l0[2]) * u, l0[3] + (l1[3] - l0[3]) * u }
					local pos = {
						m[1][1] * l[1] + m[1][2] * l[2] + m[1][3] * l[3],
						m[2][1] * l[1] + m[2][2] * l[2] + m[2][3] * l[3],
						m[3][1] * l[1] + m[3][2] * l[2] + m[3][3] * l[3],
					}
					local leaf: any = {
						Name = "Handle",
						ClassName = "Pose",
						Properties = {
							Weight = 1,
							CFrame = { CFrame = { position = pos, orientation = m } },
							EasingStyle = Anim.poseStyle("Linear"),
							EasingDirection = Anim.poseDirection("InOut"),
						},
					}
					for c = #chain, 1, -1 do
						leaf = {
							Name = chain[c],
							ClassName = "Pose",
							Properties = {
								Weight = 0,
								CFrame = { CFrame = { position = { 0, 0, 0 }, orientation = REST_ROT } },
							},
							Children = { leaf },
						}
					end
					leaf = {
						Name = rig.root,
						ClassName = "Pose",
						Properties = {
							Weight = 0,
							CFrame = { CFrame = { position = { 0, 0, 0 }, orientation = REST_ROT } },
						},
						Children = { leaf },
					}
					table.insert(keyframes, {
						Name = "Keyframe",
						ClassName = "Keyframe",
						Properties = { Time = t0 + (t1 - t0) * u },
						Children = { leaf },
					})
				end
			end
		end
	end
	-- an event between keys gets a keyframe of its own holding only the marker: a joint absent from a keyframe is
	-- interpolated across it (the Animation Editor writes sparse keyframes the same way)
	for i, ev in clip.events do
		if type(ev.t) == "number" and not marked[i] then
			table.insert(keyframes, {
				Name = "Keyframe",
				ClassName = "Keyframe",
				Properties = { Time = ev.t },
				Children = {
					{ Name = ev.name, ClassName = "KeyframeMarker", Properties = { Value = tostring(ev.value or "") } },
				},
			})
		end
	end
	table.sort(keyframes, function(a, b)
		return a.Properties.Time < b.Properties.Time
	end)
	local model = {
		ClassName = "KeyframeSequence",
		Properties = { Loop = clip.loop == true, Priority = clip.priority or "Action" },
		Children = keyframes,
	}
	return model,
		{
			rig = rigName,
			frames = frames,
			events = clip.events,
			joints = rig.joints,
			sizes = rig.sizes,
			order = rig.order,
			root = rig.root,
			moved = moved,
			clip = clip,
		},
		issues
end

-- spec -> (model, data, issues) for one rig: the v1 entry point, kept for callers and tests
function Anim.compile(spec: any, target: string?): (any?, any, { Issue })
	local clip, issues = Anim.clipFromSpec(spec)
	if not clip then
		return nil, nil, issues
	end
	local rigName = target or "R6"
	if rigName == "R6" and clip.rig == "R15" then
		local folded, foldIssues = Anim.foldToR6(clip)
		clip = folded
		for _, i in foldIssues do
			table.insert(issues, i)
		end
	end
	local model, data, more = Anim.modelFromClip(clip, rigName)
	for _, i in more do
		table.insert(issues, i)
	end
	return model, data, issues
end

return Anim

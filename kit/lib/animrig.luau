-- animrig.luau — rigs READ FROM THE ENGINE + the CFrame maths and forward kinematics the animation pipeline runs on.
-- kit/anim/rigs/<rig>.json (R6, R15, any custom rig) are written by `kit anim rig --from <dump>` from the Luau in
-- kit/anim/rig_probe.luau run inside Studio through the Studio MCP: every joint's C0/C1 (Motor6D) or rig attachments
-- (AnimationConstraint), every part's class, size and rest offset. Nothing about a rig is typed by hand here.
-- R15 (and the newer AnimationConstraint avatars): every joint frame is axis-aligned (rig attachments with identity
-- rotation), so a character-space rotation IS the joint transform; the attachment positions are the pivots, and
-- Rig.fk places every part exactly where the engine does (checked against the probe's rest offsets in the specs).
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Rig = {}

export type Issue = { path: string, message: string, severity: string }
-- a CFrame as Roblox's GetComponents(): { x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 }
export type CFrame12 = { number }
export type Joint = { joint: string, parent: string, c0: CFrame12, c1: CFrame12 }
export type Rig = {
	schema: number,
	rig: string,
	root: string,
	jointType: string?,
	hipHeight: number?,
	order: { string }, -- parts, parents before children
	joints: { [string]: Joint },
	sizes: { [string]: { number } },
	rest: { [string]: CFrame12 }, -- each part's rest CFrame relative to the root (engine-read)
	classes: { [string]: string }?,
	source: any?,
}

Rig.RIG_DIR = "kit/anim/rigs"
Rig.IDENTITY = { 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1 } :: CFrame12
local IDENTITY = Rig.IDENTITY

-- an R6 joint name in a spec drives this R15 joint (the R6 limb is one piece: elbow/knee stay straight unless the
-- spec also names the R15 joint, e.g. "RightLowerArm")
Rig.R15_FROM_R6 = {
	Torso = "LowerTorso",
	Head = "Head",
	["Right Arm"] = "RightUpperArm",
	["Left Arm"] = "LeftUpperArm",
	["Right Leg"] = "RightUpperLeg",
	["Left Leg"] = "LeftUpperLeg",
}
-- the R6 limb an R15 joint lands on (UpperTorso folds into Torso: an R6 torso is one piece)
Rig.R6_FROM_R15 = {
	LowerTorso = "Torso",
	UpperTorso = "Torso",
	Head = "Head",
	RightUpperArm = "Right Arm",
	LeftUpperArm = "Left Arm",
	RightUpperLeg = "Right Leg",
	LeftUpperLeg = "Left Leg",
}

-- ---------------------------------------------------------------- 3x3 math (rotation matrices as nested rows)
local function rotOf(c: CFrame12): { { number } }
	return { { c[4], c[5], c[6] }, { c[7], c[8], c[9] }, { c[10], c[11], c[12] } }
end
local function mul(a: { { number } }, b: { { number } }): { { number } }
	local o = {}
	for i = 1, 3 do
		o[i] = {}
		for j = 1, 3 do
			o[i][j] = a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j]
		end
	end
	return o
end
local function transpose(a: { { number } }): { { number } }
	return { { a[1][1], a[2][1], a[3][1] }, { a[1][2], a[2][2], a[3][2] }, { a[1][3], a[2][3], a[3][3] } }
end
local function angles(r: { number }): { { number } }
	local x, y, z = math.rad(r[1] or 0), math.rad(r[2] or 0), math.rad(r[3] or 0)
	local rx = { { 1, 0, 0 }, { 0, math.cos(x), -math.sin(x) }, { 0, math.sin(x), math.cos(x) } }
	local ry = { { math.cos(y), 0, math.sin(y) }, { 0, 1, 0 }, { -math.sin(y), 0, math.cos(y) } }
	local rz = { { math.cos(z), -math.sin(z), 0 }, { math.sin(z), math.cos(z), 0 }, { 0, 0, 1 } }
	return mul(mul(rx, ry), rz)
end
local function applyT(m: { { number } }, v: { number }): { number } -- m^T * v
	return {
		m[1][1] * v[1] + m[2][1] * v[2] + m[3][1] * v[3],
		m[1][2] * v[1] + m[2][2] * v[2] + m[3][2] * v[3],
		m[1][3] * v[1] + m[2][3] * v[2] + m[3][3] * v[3],
	}
end
local function round(m: { { number } }): { { number } }
	for i = 1, 3 do
		for j = 1, 3 do
			m[i][j] = math.floor(m[i][j] * 1e6 + 0.5) / 1e6
		end
	end
	return m
end
Rig.angles = angles

-- ---------------------------------------------------------------- CFrame math on the 12-component form
local CF = {}
Rig.CF = CF

-- a CFrame from a 3x3 rotation (nested rows) and a position
function CF.fromRot(rot: { { number } }, pos: { number }?): CFrame12
	local p = pos or { 0, 0, 0 }
	return {
		p[1],
		p[2],
		p[3],
		rot[1][1],
		rot[1][2],
		rot[1][3],
		rot[2][1],
		rot[2][2],
		rot[2][3],
		rot[3][1],
		rot[3][2],
		rot[3][3],
	}
end

-- CFrame.new(x, y, z) * CFrame.Angles(rad x, y, z) — degrees in, like the spec
function CF.angles(deg: { number }, pos: { number }?): CFrame12
	return CF.fromRot(angles(deg), pos)
end

-- a * b (apply b in a's space, like Roblox's CFrame multiplication)
function CF.mul(a: CFrame12, b: CFrame12): CFrame12
	local out = table.create(12, 0)
	for i = 0, 2 do
		for j = 0, 2 do
			out[4 + i * 3 + j] = a[4 + i * 3] * b[4 + j] + a[5 + i * 3] * b[7 + j] + a[6 + i * 3] * b[10 + j]
		end
	end
	out[1] = a[1] + a[4] * b[1] + a[5] * b[2] + a[6] * b[3]
	out[2] = a[2] + a[7] * b[1] + a[8] * b[2] + a[9] * b[3]
	out[3] = a[3] + a[10] * b[1] + a[11] * b[2] + a[12] * b[3]
	return out
end

-- a:Inverse()
function CF.inv(a: CFrame12): CFrame12
	local out = table.create(12, 0)
	for i = 0, 2 do
		for j = 0, 2 do
			out[4 + i * 3 + j] = a[4 + j * 3 + i]
		end
	end
	out[1] = -(a[4] * a[1] + a[7] * a[2] + a[10] * a[3])
	out[2] = -(a[5] * a[1] + a[8] * a[2] + a[11] * a[3])
	out[3] = -(a[6] * a[1] + a[9] * a[2] + a[12] * a[3])
	return out
end

-- the position part
function CF.pos(a: CFrame12): { number }
	return { a[1], a[2], a[3] }
end

-- the rotation part as nested rows
function CF.rot(a: CFrame12): { { number } }
	return rotOf(a)
end

-- ---------------------------------------------------------------- rigs (engine data)
local rigCache: { [string]: Rig } = {}

-- the rig data for "R6" | "R15" | a custom rig (kit/anim/rigs/<name>.json, lower-case)
function Rig.rig(name: string): Rig
	local key = string.lower(name)
	if rigCache[key] then
		return rigCache[key]
	end
	local path = `{Rig.RIG_DIR}/{key}.json`
	if not fs.isFile(path) then
		error(
			`no rig data for "{name}" ({path}) — read it from the engine: lune run kit anim rig --probe (run the Luau in Studio through the MCP), then lune run kit anim rig --from <saved json>`
		)
	end
	local rig = serde.decode("json", fs.readFile(path))
	rigCache[key] = rig
	return rig
end

-- the rigs the kit knows (file names under kit/anim/rigs)
function Rig.rigs(): { string }
	local out = {}
	if fs.isDir(Rig.RIG_DIR) then
		for _, f in fs.readDir(Rig.RIG_DIR) do
			if string.sub(f, -5) == ".json" then
				table.insert(out, string.sub(f, 1, -6))
			end
		end
	end
	table.sort(out)
	return out
end

-- Rig.RIGS.R6 / Rig.RIGS.R15 / Rig.RIGS[<custom>]: every rig file, loaded when the module loads (a file read
-- yields in Lune, and a metamethod may not yield — so no lazy __index here). `kit anim rig --from` reloads them.
Rig.RIGS = {} :: { [string]: Rig }

function Rig.loadRigs()
	table.clear(rigCache)
	table.clear(Rig.RIGS)
	for _, name in Rig.rigs() do
		local rig = Rig.rig(name)
		Rig.RIGS[rig.rig] = rig
		Rig.RIGS[name] = rig
	end
end

-- forget loaded rig data and read the files again (after `kit anim rig --from` rewrote one)
function Rig.forgetRigs()
	Rig.loadRigs()
end

-- One rig of a probe dump (kit/anim/rig_probe.luau) -> rig data. Joints come from AnimationConstraints (the newer
-- avatars: C0/C1 = the rig attachments' CFrames) or Motor6Ds (C0/C1 as set); parts give sizes and rest offsets.
function Rig.ingestRig(dump: any, source: any?): (Rig?, string?)
	if type(dump) ~= "table" or type(dump.parts) ~= "table" then
		return nil, "not a rig dump (needs parts + motors or constraints)"
	end
	local root = if type(dump.root) == "string" then dump.root else "HumanoidRootPart"
	if not dump.parts[root] then
		return nil, `the dump has no root part "{root}"`
	end
	local joints: { [string]: Joint } = {}
	local jointType = nil
	if type(dump.constraints) == "table" and #dump.constraints > 0 then
		jointType = "AnimationConstraint"
		for _, c in dump.constraints do
			if c.a0 and c.a1 and c.a0.part and c.a1.part then
				joints[c.a1.part] = { joint = c.name, parent = c.a0.part, c0 = c.a0.cframe, c1 = c.a1.cframe }
			end
		end
	elseif type(dump.motors) == "table" and #dump.motors > 0 then
		jointType = "Motor6D"
		for _, m in dump.motors do
			if m.part0 and m.part1 then
				joints[m.part1] = { joint = m.name, parent = m.part0, c0 = m.c0, c1 = m.c1 }
			end
		end
	else
		return nil, "the dump has no joints (no AnimationConstraints and no Motor6Ds)"
	end
	-- parents before children, deterministic (sorted names level by level)
	local names = {}
	for part in joints do
		table.insert(names, part)
	end
	table.sort(names)
	local order, placed = {}, { [root] = true }
	while #order < #names do
		local progressed = false
		for _, part in names do
			if not placed[part] and placed[joints[part].parent] then
				table.insert(order, part)
				placed[part] = true
				progressed = true
			end
		end
		if not progressed then
			local loose = {}
			for _, part in names do
				if not placed[part] then
					table.insert(loose, part)
				end
			end
			return nil, `joints that never reach the root {root}: {table.concat(loose, ", ")}`
		end
	end
	local sizes, rest, classes = {}, {}, {}
	for part, p in dump.parts do
		sizes[part] = p.size
		rest[part] = p.offset
		classes[part] = p.class
	end
	return {
		schema = 1,
		rig = dump.rig or "Custom",
		root = root,
		jointType = jointType,
		hipHeight = dump.hipHeight,
		order = order,
		joints = joints,
		sizes = sizes,
		rest = rest,
		classes = classes,
		source = source,
	},
		nil
end

-- forward kinematics: every part's CFrame relative to the root for joint-space transforms (Pose.CFrame per part:
-- { rot = 3x3, pos = {x, y, z} }; missing = rest). part = parent * C0 * Transform * C1^-1, as the engine does it.
function Rig.fk(rig: Rig, transforms: { [string]: { rot: { { number } }, pos: { number } } }?): { [string]: CFrame12 }
	local world: { [string]: CFrame12 } = { [rig.root] = IDENTITY }
	for _, part in rig.order do
		local j = rig.joints[part]
		local t = transforms and transforms[part]
		local tcf = if t then CF.fromRot(t.rot, t.pos) else IDENTITY
		world[part] = CF.mul(CF.mul(CF.mul(world[j.parent], j.c0), tcf), CF.inv(j.c1))
	end
	return world
end

-- character-space rotation (3x3) / offset at a joint -> the joint-space Pose transform (Motor6D.Transform)
function Rig.toJointM(jointC0: CFrame12, rot: { { number } }, pos: { number }?): ({ { number } }, { number })
	local c0 = rotOf(jointC0)
	local t = round(mul(mul(transpose(c0), rot), c0))
	local p = applyT(c0, pos or { 0, 0, 0 })
	return t, p
end

-- the same from character-space Euler degrees (the spec's [x, y, z])
function Rig.toJoint(jointC0: CFrame12, rot: { number }, pos: { number }?): ({ { number } }, { number })
	return Rig.toJointM(jointC0, angles(rot), pos)
end

-- a rotation matrix (rows) -> [x, y, z] degrees in CFrame.Angles order (Rx * Ry * Rz), rounded to 1e-4
function Rig.eulerOf(m: { { number } }): { number }
	local sy = math.clamp(m[1][3], -1, 1)
	local y = math.asin(sy)
	local x, z
	if math.abs(sy) < 0.999999 then
		x = math.atan2(-m[2][3], m[3][3])
		z = math.atan2(-m[1][2], m[1][1])
	else -- gimbal lock: put the whole turn on X
		x = math.atan2(m[3][2], m[2][2])
		z = 0
	end
	local function r(v: number): number
		return math.floor(math.deg(v) * 1e4 + 0.5) / 1e4
	end
	return { r(x), r(y), r(z) }
end

Rig.mul3 = mul
Rig.transpose3 = transpose

Rig.loadRigs()

return Rig

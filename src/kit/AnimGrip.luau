--!strict
-- AnimGrip — THE SWORD AS ITS OWN JOINT (board m39b; board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md D8).
--
-- A default R6 welds a tool to the fist (RightGrip): the blade can only point where the rigid arm points, so a
-- clip's own blade track (edge flips, the underhip's turn of the sword, wrist rolls) is lost in game. The kit's
-- strike clips key a Motor6D named "Handle" under the Right Arm (kit/anim/grip.py writes the track, kit/lib/anim.luau
-- the Pose); this module builds that joint: Part0 = Right Arm, Part1 = the weapon part named "Handle",
--   C0 = Roblox's RightGrip C0 (the hand: 1 stud down the arm, turned -90 deg about X)
--   C1 = the Handle's grip point in its own space (the middle of the tsuka; the katana model's is ~0.28 up its Y)
-- and the weapon frame: +Y along the blade to the tip, -X toward the edge (assets/models/build_katana.py).
-- Pure maths (rows of 4x4 numbers) is separate from the Instance part so the spec can test it outside Studio.
--
--   AnimGrip.attach(character, handlePart, gripPoint?, handOffset?)  -> Motor6D (replaces RightGrip if a Tool made one)
--     handOffset: studs up the handle (+Y) from the grip point to the RIGHT hand, for clips exported with their
--     joint origin at the hand (a move's "grip_origin": "hand"; the contract's animSword gripOrigin, = the hand
--     spacing / 2): their poses carry no slide, so a fade toward an idle turns the blade about the hand
--   AnimGrip.detach(character)                           -> restores a plain weld-free arm

local AnimGrip = {}

type M4 = { { number } }

-- RightGrip.C0 = CFrame.new(0, -1, 0, 1, 0, 0, 0, 0, 1, 0, -1, 0)
AnimGrip.GRIP_C0 = {
	{ 1, 0, 0, 0 },
	{ 0, 0, 1, -1 },
	{ 0, -1, 0, 0 },
	{ 0, 0, 0, 1 },
} :: M4

local function mul(a: M4, b: M4): M4
	local out: M4 = {}
	for i = 1, 4 do
		out[i] = {}
		for j = 1, 4 do
			local s = 0
			for k = 1, 4 do
				s += a[i][k] * b[k][j]
			end
			out[i][j] = s
		end
	end
	return out
end

-- the inverse of a rigid 4x4 (rotation + translation)
local function inv(m: M4): M4
	local r: M4 = {}
	for i = 1, 3 do
		r[i] = {}
		for j = 1, 3 do
			r[i][j] = m[j][i]
		end
	end
	for i = 1, 3 do
		r[i][4] = -(r[i][1] * m[1][4] + r[i][2] * m[2][4] + r[i][3] * m[3][4])
	end
	r[4] = { 0, 0, 0, 1 }
	return r
end

AnimGrip.mul = mul
AnimGrip.inv = inv

-- the Handle joint's Transform that puts the weapon at `handle` (character space) with the Right Arm at `arm`
function AnimGrip.transform(arm: M4, handle: M4): M4
	return mul(inv(mul(arm, AnimGrip.GRIP_C0)), handle)
end

-- where the weapon ends up for an arm frame and a joint Transform (C1 = identity: the weapon frame at its grip point)
function AnimGrip.place(arm: M4, transform: M4): M4
	return mul(mul(arm, AnimGrip.GRIP_C0), transform)
end

-- ---------------------------------------------------------------- the game side (Instances)
-- builds (or reuses) the Motor6D "Handle" joint; `gripPoint` = the grip's place in the handle's own space
function AnimGrip.attach(character: Model, handle: BasePart, gripPoint: Vector3?, handOffset: number?): Motor6D?
	local arm = character:FindFirstChild("Right Arm") :: BasePart?
	if not arm then
		return nil
	end
	handle.Name = "Handle" -- the KeyframeSequence's Pose is named after Part1
	local weld = arm:FindFirstChild("RightGrip")
	if weld then
		weld:Destroy() -- the Tool's weld would fight the animated joint
	end
	-- one expression, never nil (the type gate rejected a cast of a maybe-nil motor - KIT FOUNDATION, 2026-10-22)
	local found = arm:FindFirstChild("Handle")
	local m: Motor6D = if found and found:IsA("Motor6D") then found else Instance.new("Motor6D")
	m.Name = "Handle"
	m.Part0 = arm
	m.Part1 = handle
	m.C0 = CFrame.new(0, -1, 0, 1, 0, 0, 0, 0, 1, 0, -1, 0) -- = AnimGrip.GRIP_C0 (built here: the spec runs outside Roblox)
	m.C1 = CFrame.new((gripPoint or Vector3.zero) + Vector3.new(0, handOffset or 0, 0))
	m.Parent = arm
	return m
end

function AnimGrip.detach(character: Model)
	local arm = character:FindFirstChild("Right Arm")
	local motor = arm and arm:FindFirstChild("Handle")
	if motor and motor:IsA("Motor6D") then
		motor:Destroy()
	end
end

return AnimGrip

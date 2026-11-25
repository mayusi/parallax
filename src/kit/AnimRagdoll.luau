--!strict
-- AnimRagdoll — KNOCKDOWNS by physics (AAA gaps v2 D13; board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md). Pros hand a
-- launched / knocked-down body to physics and blend back to animation for the get-up (Euphoria / active ragdolls).
-- R6: every Motor6D between the body parts gives way to a BallSocketConstraint (limited cones, so limbs fold the R6
-- way), the push is applied, and after `seconds` the motors come back and the humanoid stands up (GettingUp).
-- Played on the server (Moves calls it on a hit with onHit.knockdown); a player's body is owned by its client, so the
-- server asks the network owner to be the server for the duration (physics then replicates to everyone).
--
--   AnimRagdoll.knock(character, push: Vector3, seconds, opts?)   -- push = studs/s on the HumanoidRootPart
--     opts.blend     seconds of the GET-UP BLEND (default 0.35, at most 1; 0 = the motors snap back)
--     opts.getUp     { back = "<clip>", front = "<clip>" }: the get-up clip for a body on its back / on its front
--                    (AnimRules.getUpSide), played through src/kit/Anim when the motors come back
--   AnimRagdoll.watch(character)   -- ON A CLIENT, for a character it shows: blends that character's get-ups there
--
-- THE GET-UP BLEND (the owner's method lists: active ragdoll): when the motors come back, each joint does not jump
-- from where the ragdoll left it to the pose the Animator plays. Its offset from that pose is taken ONCE
-- (AnimRules.getUpOffset) and let go over `blend` seconds, laid on whatever the Animator plays meanwhile
-- (AnimRules.getUpStep: no jump, no overshoot, arriving with no speed).
-- WHERE IT RUNS: a joint's pose (Motor6D.Transform) does not travel between machines - each machine's Animator
-- writes its own. So the blend a player SEES must run on that player's machine: `watch` does it there (the kit's
-- client script src/kit/client/AnimRoot.client.luau calls it for every player's character; call it yourself for an
-- NPC). The server writes the blend's length on the character (attribute KitGetUpBlend) and blends its own copy too
-- (that copy is what its hit checks read).
-- THE ROOT'S TURN TOO (V4 4.4 / 13.4.3): the Humanoid's GettingUp stands the root up by itself in a few frames; the
-- root joint (root -> torso) is given that turn back and lets it go over the same blend (AnimRules.rootHold), so
-- the body rises instead of snapping upright with its root.
--
-- Studio-unproven (written 2026-10-22; the blend 2026-11-14): prove it in a playtest before relying on it.

local RunService = game:GetService("RunService")

local AnimLayers = require(script.Parent.AnimLayers)
local AnimRules = require(script.Parent.AnimRules)

local AnimRagdoll = {}

export type KnockOptions = { blend: number?, getUp: { back: string?, front: string? }? }

AnimRagdoll.BLEND = 0.35

-- a CFrame's turn as { x, y, z, w }, and back
local function quatOf(cf: CFrame): { number }
	local axis, angle = cf:ToAxisAngle()
	local s = math.sin(angle / 2)
	return { axis.X * s, axis.Y * s, axis.Z * s, math.cos(angle / 2) }
end

local function poseOf(cf: CFrame): AnimRules.JointPose
	return { turn = quatOf(cf), slide = { cf.Position.X, cf.Position.Y, cf.Position.Z } }
end

local function cfOf(p: AnimRules.JointPose): CFrame
	return CFrame.new(p.slide[1], p.slide[2], p.slide[3], p.turn[1], p.turn[2], p.turn[3], p.turn[4])
end

-- (the engine keeps Transform in single precision: a value read back is never exactly the one written)
local function sameCF(a: CFrame, b: CFrame): boolean
	return (a.Position - b.Position).Magnitude < 1e-3
		and (a.XVector - b.XVector).Magnitude < 1e-4
		and (a.YVector - b.YVector).Magnitude < 1e-4
end

-- where the ragdoll left each joint, as the Transform that would hold it there: Part1 = Part0 * C0 * T * C1^-1
local function ragOf(motors: { Motor6D }): { [Motor6D]: CFrame }
	local rag: { [Motor6D]: CFrame } = {}
	for _, m in motors do
		if m.Part0 and m.Part1 then
			rag[m] = (m.Part0.CFrame * m.C0):Inverse() * (m.Part1.CFrame * m.C1)
		end
	end
	return rag
end

local blends: { [Model]: RBXScriptConnection } = setmetatable({}, { __mode = "k" }) :: any
local leaving: { [Model]: () -> () } = setmetatable({}, { __mode = "k" }) :: any -- a running blend's way off its joints

-- the motors are back: let each joint's offset from the played pose go over `blend` seconds
local function getUpBlend(character: Model, rag: { [Motor6D]: CFrame }, blend: number)
	local running = blends[character]
	if running then
		running:Disconnect() -- (one blend a body: two would each take the other's write for the Animator's)
		local off = leaving[character]
		if off then
			off() -- (the blend it replaces leaves the joints' record: left on it, the last layer would never give them back)
		end
	end
	local offsets: { [string]: AnimRules.GetUpOffset }? = nil
	-- (the joints' ONE record, shared with src/kit/Anim's layers - AnimLayers.stackOf: keeping its own, this blend
	-- and a look-at on the neck each took the other's write for the clip's and the turn added up every frame)
	local joined: { [Motor6D]: boolean } = {}
	local started = os.clock()
	-- THE ROOT'S OWN TURN (V4 4.4 / 13.4.3): the root joint's turn since this moment is held back and let go over the
	-- blend (AnimRules.rootHold) - GettingUp stands the root up in a few frames and the body, rigid on it, snapped up
	local rootPart = character:FindFirstChild("HumanoidRootPart")
	local rootJoint: Motor6D? = nil
	if rootPart and rootPart:IsA("BasePart") then
		for _, d in character:GetDescendants() do
			if d:IsA("Motor6D") and d.Part0 == rootPart and d.Part1 and not rag[d] then
				rootJoint = d
				break
			end
		end
	end
	local rootStart = if rootJoint then quatOf((rootPart :: BasePart).CFrame) else nil
	local conn: RBXScriptConnection
	local function leave()
		for m in joined do
			local back = AnimLayers.stackRelease(AnimLayers.stackOf(m), m.Transform, sameCF)
			if back then
				m.Transform = back
			end
		end
		table.clear(joined)
	end
	conn = RunService.Stepped:Connect(function(frame: number)
		local t = os.clock() - started
		if t >= blend or not character.Parent then
			conn:Disconnect()
			if blends[character] == conn then
				blends[character] = nil
			end
			leave()
			return
		end
		-- what the Animator plays now (a joint no track drives still holds our last write: its clean value then)
		local clip: { [string]: AnimRules.JointPose } = {}
		-- (each joint's base this frame: its clean value when it still holds the layers' last write, what it holds when
		-- a layer before this blend wrote on it this frame. The offset of the layers before is measured from THIS -
		-- measured from what the joint holds, a joint no track drives took the blend's own last write for another
		-- layer's and laid it on again every frame: Studio 2026-11-20, a get-up from 4 deg tilted the torso to 79 deg)
		local bases: { [Motor6D]: CFrame } = {}
		for m in rag do
			local stack = AnimLayers.stackOf(m)
			if not joined[m] then
				joined[m] = true
				stack.users += 1
			end
			-- (the clip's own pose: the clean value under every layer, whichever of them ran first this frame)
			bases[m] = AnimLayers.stackBase(stack, m.Transform, frame, sameCF, joined)
			clip[m.Name] = poseOf(stack.clean or m.Transform)
		end
		if not offsets then
			local made: { [string]: AnimRules.GetUpOffset } = {}
			offsets = made
			for m, r in rag do
				local c = clip[m.Name]
				local rp = r.Position
				made[m.Name] = {
					turn = AnimRules.getUpOffset(quatOf(r), c.turn),
					slide = { rp.X - c.slide[1], rp.Y - c.slide[2], rp.Z - c.slide[3] },
				}
			end
		end
		local out = AnimRules.getUpStep(offsets :: any, clip, blend, t)
		for m in rag do
			local p = out[m.Name]
			if p and m.Parent then
				local cf = cfOf(p)
				-- (a layer that ran before this blend in the frame put its offset on the joint: kept on top)
				local stack = AnimLayers.stackOf(m)
				local over = if stack.clean then (bases[m] or m.Transform) * stack.clean:Inverse() else CFrame.new()
				cf = if sameCF(over, CFrame.new()) then cf else over * cf
				m.Transform = cf
				AnimLayers.stackWrite(stack, cf)
			end
		end
		local rj = rootJoint
		if rj and rootStart and rj.Parent and (rootPart :: BasePart).Parent then
			local stack = AnimLayers.stackOf(rj)
			if not joined[rj] then
				joined[rj] = true
				stack.users += 1
			end
			local base = AnimLayers.stackBase(stack, rj.Transform, frame, sameCF, joined)
			local q = AnimRules.rootHold(rootStart, quatOf((rootPart :: BasePart).CFrame), blend, t)
			-- torso = root * C0 * T * C1^-1, wanted root * hold * C0 * clip * C1^-1: T = C0^-1 * hold * C0 * clip
			local c0 = rj.C0
			local cf = c0:Inverse() * CFrame.new(0, 0, 0, q[1], q[2], q[3], q[4]) * c0 * (stack.clean or rj.Transform)
			local over = if stack.clean then base * stack.clean:Inverse() else CFrame.new()
			cf = if sameCF(over, CFrame.new()) then cf else over * cf
			rj.Transform = cf
			AnimLayers.stackWrite(stack, cf)
		end
	end)
	blends[character] = conn
	leaving[character] = leave
end

local CONE: { [string]: number } = {
	["Neck"] = 35,
	["Left Shoulder"] = 80,
	["Right Shoulder"] = 80,
	["Left Hip"] = 55,
	["Right Hip"] = 55,
}

local active: { [Model]: boolean } = setmetatable({}, { __mode = "k" }) :: any

local function blendOf(seconds: any): number
	if type(seconds) ~= "number" or seconds ~= seconds then
		return AnimRagdoll.BLEND
	end
	return math.clamp(seconds, 0, 1)
end

-- ON A CLIENT: blend this character's get-ups where they are seen. The moment its ragdoll's motors come back
-- (their Enabled turns true, from the server), the joints are read where the ragdoll left them on THIS machine and
-- eased to what its Animator plays. Returns a function that stops watching.
function AnimRagdoll.watch(character: Model): () -> ()
	local conns: { RBXScriptConnection } = {}
	local pending = false
	local function motors(): { Motor6D }
		local out: { Motor6D } = {}
		for _, d in character:GetDescendants() do
			if d:IsA("Motor6D") and CONE[d.Name] then
				table.insert(out, d)
			end
		end
		return out
	end
	local function hook(m: Motor6D)
		table.insert(
			conns,
			m:GetPropertyChangedSignal("Enabled"):Connect(function()
				if not m.Enabled or pending then
					return
				end
				pending = true
				local rag = ragOf(motors()) -- (now: before the motors pull the parts back)
				local blend = blendOf(character:GetAttribute("KitGetUpBlend"))
				task.defer(function()
					pending = false
					if blend > 0 and character.Parent then
						getUpBlend(character, rag, blend)
					end
				end)
			end)
		)
	end
	for _, m in motors() do
		hook(m)
	end
	table.insert(
		conns,
		character.DescendantAdded:Connect(function(d)
			if d:IsA("Motor6D") and CONE[d.Name] then
				hook(d)
			end
		end)
	)
	return function()
		for _, c in conns do
			c:Disconnect()
		end
	end
end

function AnimRagdoll.knock(character: Model, push: Vector3, seconds: number, opts: KnockOptions?)
	if active[character] then
		return
	end
	local hum = character:FindFirstChildOfClass("Humanoid")
	local root = character:FindFirstChild("HumanoidRootPart")
	if not hum or not root or not root:IsA("BasePart") then
		return
	end
	active[character] = true
	local rootPart = root :: BasePart
	local saved: { { motor: Motor6D, socket: BallSocketConstraint, a0: Attachment, a1: Attachment } } = {}
	for _, d in character:GetDescendants() do
		if d:IsA("Motor6D") and CONE[d.Name] and d.Part0 and d.Part1 then
			local m = d :: Motor6D
			local a0 = Instance.new("Attachment")
			a0.CFrame = m.C0
			a0.Parent = m.Part0
			local a1 = Instance.new("Attachment")
			a1.CFrame = m.C1
			a1.Parent = m.Part1
			local socket = Instance.new("BallSocketConstraint")
			socket.Attachment0, socket.Attachment1 = a0, a1
			socket.LimitsEnabled = true
			socket.UpperAngle = CONE[m.Name]
			socket.TwistLimitsEnabled = true
			socket.TwistLowerAngle, socket.TwistUpperAngle = -30, 30
			socket.Parent = m.Part0
			m.Enabled = false
			table.insert(saved, { motor = m, socket = socket, a0 = a0, a1 = a1 })
		end
	end
	pcall(function()
		rootPart:SetNetworkOwner(nil)
	end)
	hum.PlatformStand = true
	rootPart.AssemblyLinearVelocity = push
	task.delay(math.max(0.2, seconds), function()
		local blend = blendOf(if opts then opts.blend else nil)
		character:SetAttribute("KitGetUpBlend", blend) -- (each client's AnimRagdoll.watch blends by it)
		local back: { Motor6D } = {}
		for _, s in saved do
			if s.motor.Parent then
				table.insert(back, s.motor)
			end
		end
		-- on its back or on its front, read BEFORE the motors pull the body up
		local torso = character:FindFirstChild("Torso")
		local side = AnimRules.getUpSide(
			if torso and torso:IsA("BasePart") then torso.CFrame.LookVector:Dot(Vector3.yAxis) else 1
		)
		if blend > 0 and character.Parent then
			getUpBlend(character, ragOf(back), blend) -- (read where the ragdoll left the parts: before the motors return)
		end
		for _, s in saved do
			if s.motor.Parent then
				s.motor.Enabled = true
			end
			s.socket:Destroy()
			s.a0:Destroy()
			s.a1:Destroy()
		end
		if hum.Parent then
			hum.PlatformStand = false
			hum:ChangeState(Enum.HumanoidStateType.GettingUp)
			local clipName = if opts and opts.getUp then (opts.getUp :: any)[side] else nil
			if type(clipName) == "string" then
				local okA, Anim = pcall(function()
					return (require :: any)(script.Parent:FindFirstChild("Anim"))
				end)
				if okA and Anim then
					Anim.play(hum, clipName, blend)
				end
			end
		end
		pcall(function()
			local Players = game:GetService("Players")
			local player = Players:GetPlayerFromCharacter(character)
			if player and rootPart.Parent then
				rootPart:SetNetworkOwner(player)
			end
		end)
		active[character] = nil
	end)
end

return AnimRagdoll

--!strict
-- AnimAim (ReplicatedStorage.kit.AnimAim) — A HELD GUN AT REST FOLLOWS THE LOOK (LIMITATIONS_FIXES_V4 4.4 / 13.4.3:
-- "drive idle barrel pitch/yaw in Anim.lookAt"; the owner's V3 list F.1b: the head and torso look, the gun did not).
--   local stop = AnimAim.barrel(character, target, { muzzle = gun.Muzzle, arm = "Right Arm" })
--   target: a BasePart, a Vector3, or a function giving one (nil: nothing) - the same target Anim.lookAt is given
--   muzzle: a BasePart or an Attachment whose LookVector is the barrel's way (it rides the holding arm)
--   arm: "Right Arm" (default) | "Left Arm";  maxYaw 35, maxPitch 40 (degrees the shoulder may be turned);
--   halflife 0.15 (seconds: the spring);  idle () -> 0..1 (default: no track of Action priority or higher plays)
-- While the body is IDLE the holding arm is turned at its shoulder by AnimLayers.barrelTurn - the barrel's yaw and
-- pitch to the target from where the CLIP holds it, clamped, a target behind let go - on a spring; an attack, a
-- reload or a hit (an Action track) takes the arm back to the clip on the same spring. A layer on the joints' ONE
-- record (AnimLayers.stackOf: what Anim's look-at, additive and feet share): laid over whatever the clip and the
-- layers before it wrote this frame, given back when it stops. stop(): eases out, then lets go; stop(true): at once.
-- Like every layer, it shows on the machine that runs it: call it where the body is seen (each client).
local RunService = game:GetService("RunService")

local AnimFeel = require(script.Parent.AnimFeel)
local AnimLayers = require(script.Parent.AnimLayers)

local AnimAim = {}

export type BarrelOptions = {
	muzzle: BasePart | Attachment,
	arm: string?,
	maxYaw: number?,
	maxPitch: number?,
	halflife: number?,
	idle: (() -> number)?,
}
export type Target = BasePart | Vector3 | (() -> (BasePart | Vector3)?)

-- (the engine keeps Transform in single precision: the value read back is never exactly the one written)
local function sameCF(a: CFrame, b: CFrame): boolean
	return (a.Position - b.Position).Magnitude < 1e-3
		and (a.XVector - b.XVector).Magnitude < 1e-4
		and (a.YVector - b.YVector).Magnitude < 1e-4
end

function AnimAim.barrel(character: Model, target: Target, opts: BarrelOptions): (immediate: boolean?) -> ()
	local torso = character:FindFirstChild("Torso")
	local muzzle = opts and opts.muzzle
	if not torso or not torso:IsA("BasePart") or not muzzle then
		return function() end
	end
	local body = torso :: BasePart
	local s = body:FindFirstChild(if opts.arm == "Left Arm" then "Left Shoulder" else "Right Shoulder")
	if not s or not s:IsA("Motor6D") then
		return function() end
	end
	local shoulder = s :: Motor6D
	local hum = character:FindFirstChildOfClass("Humanoid")
	local animator = hum and hum:FindFirstChildOfClass("Animator")
	local function idle(): number
		if opts.idle then
			local v = opts.idle()
			return if v == v then math.clamp(v, 0, 1) else 0
		end
		if not animator then
			return 1
		end
		for _, tr in animator:GetPlayingAnimationTracks() do
			if tr.Priority.Value >= Enum.AnimationPriority.Action.Value and tr.WeightCurrent > 0.05 then
				return 0 -- (an attack, a reload, a hit: the clip's own arm)
			end
		end
		return 1
	end
	local yawS: AnimFeel.Spring = { x = 0, v = 0 }
	local pitchS: AnimFeel.Spring = { x = 0, v = 0 }
	local joined: { [Motor6D]: boolean } = {}
	local stopped, leaving = false, nil :: number?
	local conn: RBXScriptConnection
	local function finish()
		if stopped then
			return
		end
		stopped = true
		conn:Disconnect()
		for m in joined do
			local back = AnimLayers.stackRelease(AnimLayers.stackOf(m), m.Transform, sameCF)
			if back then
				m.Transform = back
			end
		end
		table.clear(joined)
	end
	conn = RunService.Stepped:Connect(function(frame: number, dt: number)
		if stopped then
			return
		end
		if not shoulder.Parent or not character.Parent then
			finish()
			return
		end
		local stack = AnimLayers.stackOf(shoulder)
		if not joined[shoulder] then
			joined[shoulder] = true
			stack.users += 1
		end
		-- the shoulder as the clip (and the layers before this one) has it this frame
		local was = AnimLayers.stackBase(stack, shoulder.Transform, frame, sameCF, joined)
		local now: (BasePart | Vector3)? = if leaving
			then nil
			elseif type(target) == "function" then target()
			else target
		local yaw, pitch = 0, 0
		if now and muzzle.Parent then
			local at = if typeof(now) == "Vector3" then now :: Vector3 else (now :: BasePart).Position
			local mcf = if muzzle:IsA("Attachment")
				then (muzzle :: Attachment).WorldCFrame
				else (muzzle :: BasePart).CFrame
			-- (the muzzle as the CLIP holds it: last frame's turn - about the shoulder, in the torso's frame - taken
			-- off what the part shows)
			local last = CFrame.Angles(0, yawS.x, 0) * CFrame.Angles(pitchS.x, 0, 0)
			local pivot = shoulder.C0.Position
			local dir = last:VectorToObjectSpace(body.CFrame:VectorToObjectSpace(mcf.LookVector))
			local pos = pivot + last:VectorToObjectSpace(body.CFrame:PointToObjectSpace(mcf.Position) - pivot)
			local to = body.CFrame:PointToObjectSpace(at) - pos
			yaw, pitch = AnimLayers.barrelTurn(dir.X, dir.Y, dir.Z, to.X, to.Y, to.Z, opts.maxYaw, opts.maxPitch)
			local share = idle()
			yaw, pitch = yaw * share, pitch * share
		end
		local half = if leaving then 0.05 else (opts.halflife or 0.15)
		yawS = AnimFeel.spring(yawS, yaw, half, dt)
		pitchS = AnimFeel.spring(pitchS, pitch, half, dt)
		local r = CFrame.Angles(0, yawS.x, 0) * CFrame.Angles(pitchS.x, 0, 0)
		local c0 = shoulder.C0.Rotation
		local cf = (c0:Inverse() * r * c0) * was
		shoulder.Transform = cf
		AnimLayers.stackWrite(stack, cf)
		if leaving and ((math.abs(yawS.x) < 0.01 and math.abs(pitchS.x) < 0.01) or os.clock() - leaving > 0.5) then
			finish()
		end
	end)
	return function(immediate: boolean?)
		if immediate or stopped then
			finish()
		else
			leaving = leaving or os.clock()
		end
	end
end

return AnimAim

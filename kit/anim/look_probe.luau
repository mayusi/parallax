-- look_probe.luau — run INSIDE Roblox Studio (Studio MCP: execute_luau, datamodel_type = "Edit") by `kit anim look <Name>`:
-- a LIVE loop of the clip on a fresh humanoid of its rig, far from the place's own content, on a lit pad, stepped by
-- Heartbeat in Edit mode (no Play needed) — select Workspace._kit_anim_look in the Explorer and press F to look.
-- Nothing of the place is touched; `kit anim look --stop` (or Workspace._kit_anim_look.Stop.Value = true, then
-- delete the model) removes everything. The poses come from the kit's compiled model: what the game plays.
local HttpService = game:GetService("HttpService")
local KeyframeSequenceProvider = game:GetService("KeyframeSequenceProvider")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local NAME = "Walk" -- @kit:name
local RIG = "R15" -- @kit:rig
local SPOT = { -60, 0, 60 } -- @kit:spot
local DATA_JSON = [==[{}]==] -- @kit:data

local data = HttpService:JSONDecode(DATA_JSON)
local old = Workspace:FindFirstChild("_kit_anim_look")
if old then
	old:Destroy()
end
local seq = Instance.new("KeyframeSequence")
seq.Name = NAME
seq.Loop = data.loop ~= false
seq.Priority = (Enum.AnimationPriority :: any)[data.priority or "Movement"] or Enum.AnimationPriority.Movement
for i, t in data.times do
	local kf = Instance.new("Keyframe")
	kf.Time = t
	kf.Parent = seq
	local poses = {}
	local function poseOf(n: string): Pose
		if poses[n] then
			return poses[n]
		end
		local p = Instance.new("Pose")
		p.Name = n
		p.Weight = if data.poses[n] then 1 else 0
		p.EasingStyle = Enum.PoseEasingStyle.Linear
		poses[n] = p
		if n == data.root then
			p.Parent = kf
		else
			p.Parent = poseOf(data.parent[n])
		end
		return p
	end
	poseOf(data.root)
	for n, frames in data.poses do
		local f = frames[i]
		poseOf(n).CFrame = CFrame.new(f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8], f[9], f[10], f[11], f[12])
	end
end
local model =
	Players:CreateHumanoidModelFromDescription(Instance.new("HumanoidDescription"), (Enum.HumanoidRigType :: any)[RIG])
model.Name = "_kit_anim_look"
local stop = Instance.new("BoolValue")
stop.Name = "Stop"
stop.Parent = model
local spot = Vector3.new(SPOT[1], SPOT[2], SPOT[3])
local pad = Instance.new("Part")
pad.Name = "_kit_anim_look_pad"
pad.Anchored = true
pad.Size = Vector3.new(12, 1, 12)
pad.CFrame = CFrame.new(spot - Vector3.new(0, 0.5, 0))
pad.Color = Color3.fromRGB(70, 70, 76)
pad.Material = Enum.Material.SmoothPlastic
pad.Parent = model
model.Parent = Workspace
model:PivotTo(CFrame.new(spot + Vector3.new(0, if RIG == "R6" then 3.0 else 3.2, 0)))
local root = model:FindFirstChild("HumanoidRootPart") :: BasePart?
if root then
	local lamp = Instance.new("PointLight")
	lamp.Name = "_kit_lamp"
	lamp.Brightness = 3
	lamp.Range = 24
	lamp.Shadows = false
	lamp.Parent = root
end
local humanoid = model:FindFirstChildOfClass("Humanoid") :: Humanoid
local animator = humanoid:FindFirstChildOfClass("Animator") or Instance.new("Animator")
animator.Parent = humanoid
local animation = Instance.new("Animation")
animation.AnimationId = KeyframeSequenceProvider:RegisterKeyframeSequence(seq)
local track = animator:LoadAnimation(animation)
local t0 = os.clock()
while track.Length <= 0 and os.clock() - t0 < 5 do
	task.wait(0.05)
end
seq:Destroy()
track.Looped = data.loop ~= false
track:Play(0, 1, 1)
local conn
conn = RunService.Heartbeat:Connect(function(dt)
	if stop.Value or not model.Parent then
		conn:Disconnect()
		return
	end
	animator:StepAnimations(math.min(dt, 0.05))
end)
return ("looping %s (%s) on Workspace._kit_anim_look at (%d, %d, %d): select it in the Explorer and press F; length %.2f s, %d keyframes"):format(
	NAME,
	RIG,
	SPOT[1],
	SPOT[2],
	SPOT[3],
	track.Length,
	#data.times
)

-- play_probe.luau — run INSIDE Roblox Studio (Studio MCP: execute_luau, datamodel_type = "Edit") by `kit anim play <Name>`:
-- builds the clip's KeyframeSequence from the kit's compiled model, plays it on a fresh humanoid of the clip's rig
-- through its Animator and STEPS it frame by frame (Animator:StepAnimations — Edit mode, no Play needed), returning
-- every joint's Transform per frame and every marker's time as one JSON string. Save that string to a file and run
-- `kit anim record <Name> <file>`: the engine's motion is compared with the clip, frame by frame.
-- Nothing is left in the place: the humanoid and the sequence are destroyed after the run.
local HttpService = game:GetService("HttpService")
local KeyframeSequenceProvider = game:GetService("KeyframeSequenceProvider")
local Players = game:GetService("Players")
local Workspace = game:GetService("Workspace")

local NAME = "Slash" -- @kit:name
local RIG = "R15" -- @kit:rig
local FPS = 30 -- @kit:fps
local FRAMES = 24 -- @kit:frames
local EVENTS = { "Hit" } -- @kit:events
local MODEL_JSON = [==[{}]==] -- @kit:model

local function round(x: number): number
	return math.floor(x * 1e5 + 0.5) / 1e5
end

local function cframeOf(v: any): CFrame
	local p, o = v.position, v.orientation
	return CFrame.new(p[1], p[2], p[3], o[1][1], o[1][2], o[1][3], o[2][1], o[2][2], o[2][3], o[3][1], o[3][2], o[3][3])
end

-- the Rojo JSON model -> instances
local function build(node: any): Instance
	local inst = Instance.new(node.ClassName)
	inst.Name = node.Name or node.ClassName
	for k, v in node.Properties or {} do
		if type(v) == "table" and v.CFrame then
			(inst :: any)[k] = cframeOf(v.CFrame)
		elseif k == "Priority" then
			(inst :: any)[k] = (Enum.AnimationPriority :: any)[v]
		elseif k == "EasingStyle" then
			(inst :: any)[k] = (Enum.PoseEasingStyle :: any)[v]
		elseif k == "EasingDirection" then
			(inst :: any)[k] = (Enum.PoseEasingDirection :: any)[v]
		else
			(inst :: any)[k] = v
		end
	end
	for _, c in node.Children or {} do
		build(c).Parent = inst
	end
	return inst
end

local seq = build(HttpService:JSONDecode(MODEL_JSON))
seq.Name = NAME
local model =
	Players:CreateHumanoidModelFromDescription(Instance.new("HumanoidDescription"), (Enum.HumanoidRigType :: any)[RIG])
model.Name = "_kit_anim_play"
model.Parent = Workspace
local out: any = { name = NAME, rig = RIG, fps = FPS, frames = {}, markers = {} }
local ok, err = pcall(function()
	local humanoid = model:FindFirstChildOfClass("Humanoid") :: Humanoid
	local animator = humanoid:FindFirstChildOfClass("Animator") or Instance.new("Animator")
	animator.Parent = humanoid
	local animation = Instance.new("Animation")
	animation.AnimationId = KeyframeSequenceProvider:RegisterKeyframeSequence(seq)
	local track = animator:LoadAnimation(animation)
	-- a registered sequence loads asynchronously: give it a moment (StepAnimations on an unloaded track does nothing)
	local t0 = os.clock()
	while track.Length <= 0 and os.clock() - t0 < 5 do
		task.wait(0.05)
	end
	out.length = round(track.Length)
	out.loadSeconds = round(os.clock() - t0)
	if track.Length <= 0 then
		error("the animation never loaded (track.Length stayed 0 after 5 s)")
	end
	-- every joint by the part it moves (Motor6D or AnimationConstraint: both carry the animated Transform)
	local joints: { [string]: any } = {}
	for _, d in model:GetDescendants() do
		if d:IsA("Motor6D") and d.Part1 then
			joints[d.Part1.Name] = d
		elseif d:IsA("AnimationConstraint") and d.Attachment1 and d.Attachment1.Parent then
			joints[d.Attachment1.Parent.Name] = d
		end
	end
	for _, name in EVENTS do
		track:GetMarkerReachedSignal(name):Connect(function(value)
			table.insert(out.markers, { name = name, t = round(track.TimePosition), value = value })
		end)
	end
	track:Play(0, 1, 1)
	animator:StepAnimations(0)
	for i = 0, FRAMES - 1 do
		if i > 0 then
			animator:StepAnimations(1 / FPS)
		end
		local rec: any = { t = round(track.TimePosition), joints = {} }
		for part, j in joints do
			local c = { j.Transform:GetComponents() }
			local rest = true
			for k, v in c do
				c[k] = round(v)
				local ident = if k <= 3 then 0 else (if k == 4 or k == 8 or k == 12 then 1 else 0)
				if math.abs(v - ident) > 1e-5 then
					rest = false
				end
			end
			if not rest then
				rec.joints[part] = c
			end
		end
		table.insert(out.frames, rec)
	end
	track:Stop(0)
end)
model:Destroy()
seq:Destroy()
if not ok then
	out.error = tostring(err)
end
return HttpService:JSONEncode(out)

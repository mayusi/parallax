-- rig_probe.luau — run INSIDE Roblox Studio (Studio MCP: execute_luau, datamodel_type = "Edit") to read rigs the way
-- the engine builds them: every joint (Motor6D C0/C1, or an AnimationConstraint's rig attachments), every part's
-- class, size and rest offset from the root. It returns ONE JSON string: save it to a file (for example
-- _artifacts/anim/rig_probe.json) and run `lune run kit anim rig --from <that file>`.
-- Nothing is left in the place: the humanoids it makes are destroyed after reading.
-- A custom rig (a creature, a weapon with joints): set TARGET to the model's path, e.g. "ReplicatedStorage.Rigs.Wolf";
-- that model is read in place (and not touched).
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local Workspace = game:GetService("Workspace")

local TARGET: string? = nil -- @kit:target

local function round(x: number): number
	return math.floor(x * 1e5 + 0.5) / 1e5
end

local function cf(c: CFrame): { number }
	local t = { c:GetComponents() }
	for i, v in t do
		t[i] = round(v)
	end
	return t
end

local function readModel(model: Model, rigName: string)
	local root = model:FindFirstChild("HumanoidRootPart") or model.PrimaryPart
	if not root or not root:IsA("BasePart") then
		error(`{model:GetFullName()} has no HumanoidRootPart / PrimaryPart`)
	end
	local out = { rig = rigName, root = root.Name, parts = {}, motors = {}, constraints = {}, attachments = {} }
	for _, p in model:GetDescendants() do
		if p:IsA("BasePart") then
			out.parts[p.Name] = {
				class = p.ClassName,
				size = { round(p.Size.X), round(p.Size.Y), round(p.Size.Z) },
				offset = cf(root.CFrame:ToObjectSpace(p.CFrame)),
			}
		elseif p:IsA("Motor6D") then
			table.insert(out.motors, {
				name = p.Name,
				parent = p.Parent and p.Parent.Name,
				part0 = p.Part0 and p.Part0.Name,
				part1 = p.Part1 and p.Part1.Name,
				c0 = cf(p.C0),
				c1 = cf(p.C1),
			})
		elseif p:IsA("AnimationConstraint") then
			local a0, a1 = p.Attachment0, p.Attachment1
			table.insert(out.constraints, {
				name = p.Name,
				parent = p.Parent and p.Parent.Name,
				a0 = a0 and a0.Parent and { part = a0.Parent.Name, name = a0.Name, cframe = cf(a0.CFrame) },
				a1 = a1 and a1.Parent and { part = a1.Parent.Name, name = a1.Name, cframe = cf(a1.CFrame) },
			})
		elseif
			p:IsA("Attachment")
			and p.Parent
			and p.Parent:IsA("BasePart")
			and string.find(p.Name, "RigAttachment")
		then
			table.insert(out.attachments, { part = p.Parent.Name, name = p.Name, cframe = cf(p.CFrame) })
		end
	end
	local hum = model:FindFirstChildOfClass("Humanoid")
	out.hipHeight = if hum then round(hum.HipHeight) else nil
	return out
end

local function readHumanoid(rigType: Enum.HumanoidRigType)
	local model = Players:CreateHumanoidModelFromDescription(Instance.new("HumanoidDescription"), rigType)
	model.Name = "_kit_rig_probe"
	model.Parent = Workspace
	local ok, out = pcall(readModel, model, rigType.Name)
	model:Destroy()
	if not ok then
		error(out)
	end
	return out
end

local result = { probe = "kit anim rig --probe", date = os.date("!%Y-%m-%d") }
if TARGET then
	local node: Instance = game
	for _, name in string.split(TARGET, ".") do
		node = node:FindFirstChild(name) or error(`no {TARGET} ({name} not found)`)
	end
	assert(node:IsA("Model"), `{TARGET} is not a Model`)
	result.custom = readModel(node, node.Name)
else
	local ok15, r15 = pcall(readHumanoid, Enum.HumanoidRigType.R15)
	local ok6, r6 = pcall(readHumanoid, Enum.HumanoidRigType.R6)
	result.r15 = if ok15 then r15 else { error = tostring(r15) }
	result.r6 = if ok6 then r6 else { error = tostring(r6) }
end
return HttpService:JSONEncode(result)

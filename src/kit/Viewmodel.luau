-- Viewmodel (ReplicatedStorage.kit.Viewmodel) — the first-person view of a held tool, with arms. CLIENT ONLY.
--   local vm = Viewmodel.new(tool, { offset = CFrame.new(0.95, -1.05, -2.3), arms = true })
--   vm:kick(1)                 recoil (kicks back + up, settles by itself; the hands ride along)
--   vm:bolt(0.75)              right hand reaches the "Bolt" anchor, works it, comes back (bolt-action cycle)
--   vm:point("Muzzle")         world position of an anchor (a.anchor in the build script) on the copy
--   vm:destroy()               on unequip (puts the real tool back on your screen)
-- The proven pattern (kit lesson "keep first-person viewmodels rigid"): a client-only copy of the tool under the
-- CAMERA (never replicated, never in physics), shrunk by `scale` and pulled closer by the same factor (identical on
-- screen, but it no longer pokes through walls), pivoted right AFTER the camera moves each frame, real tool hidden
-- on your own screen only.
-- Arms (arms = true | { skin = Color3, sleeve = Color3, glove = Color3 }): blocky R6-style arms — skin colour
-- from your character, a sleeve and a glove — whose hands are locked every frame to the tool's "Grip" (right) and
-- "Support" (left) anchors (kit firearms have both), so recoil, the equip raise and the bolt pull move the arms
-- naturally. Shoulders sit below/behind the camera, off screen.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local Viewmodel = {}
Viewmodel.__index = Viewmodel

export type ArmOptions = { skin: Color3?, sleeve: Color3?, glove: Color3? }
export type Options = {
	offset: CFrame?, -- the tool origin (grip) in camera space, at full size; default: low right, in front
	scale: number?, -- 0.2..0.5; default 0.3
	recoilBack: number?, -- studs the kick pushes back at full size (default 0.45)
	recoilPitch: number?, -- degrees the kick tilts up (default 7)
	recoilDecay: number?, -- per second (default 9)
	arms: (boolean | ArmOptions)?,
	equipTime: number?, -- seconds of the raise-into-view on creation (default 0.35; 0 = none)
}

local DEFAULT_OFFSET = CFrame.new(0.75, -0.85, -1.3)
-- shoulders in camera space at full size (below and behind the eye: never on screen)
-- placed RELATIVE TO THE GRIP (the offset): each arm leaves the screen through a bottom corner — the right one
-- bottom-right past the grip, the left one bottom-left/centre — so arms frame the gun instead of covering it
local SHOULDER = { Right = Vector3.new(2.1, -0.4, 0.65), Left = Vector3.new(-1.0, -1.75, -0.1) }
local count = 0

local function cam(): Camera
	return Workspace.CurrentCamera :: Camera
end

local function smooth(t: number): number
	t = math.clamp(t, 0, 1)
	return t * t * (3 - 2 * t)
end

local function skinColor(): Color3
	local char = Players.LocalPlayer and Players.LocalPlayer.Character
	if char then
		local colors = char:FindFirstChildOfClass("BodyColors")
		if colors then
			return colors.RightArmColor3
		end
		local arm = char:FindFirstChild("RightUpperArm") or char:FindFirstChild("Right Arm")
		if arm and arm:IsA("BasePart") then
			return arm.Color
		end
	end
	return Color3.fromRGB(234, 184, 146)
end

local function block(name: string, size: Vector3, color: Color3, material: Enum.Material, parent: Instance): BasePart
	local p = Instance.new("Part")
	p.Name = name
	p.Size = size
	p.Color = color
	p.Material = material
	p.Anchored = true
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.CastShadow = false
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

function Viewmodel.new(tool: Tool, options: Options?)
	local opts: Options = options or {}
	local scale = opts.scale or 0.3
	local handle = tool:FindFirstChild("Handle") :: BasePart?
	assert(handle, "[Viewmodel] the tool has no Handle")
	local model = Instance.new("Model")
	count += 1
	local bindName = "KitViewmodel" .. count
	model.Name = "Viewmodel"
	local root = (handle :: BasePart):Clone()
	for _, c in root:GetChildren() do
		if not (c:IsA("Attachment") or c:IsA("DataModelMesh") or c:IsA("SurfaceAppearance")) then
			c:Destroy()
		end
	end
	root.Parent = model
	model.PrimaryPart = root
	local originals: { BasePart } = { handle :: BasePart }
	for _, part in tool:GetDescendants() do
		if part:IsA("BasePart") and part ~= handle then
			table.insert(originals, part)
			local copy = part:Clone()
			for _, c in copy:GetChildren() do
				if c:IsA("JointInstance") or c:IsA("WeldConstraint") or c:IsA("Script") or c:IsA("Sound") then
					c:Destroy()
				end
			end
			copy.CFrame = root.CFrame * (handle :: BasePart).CFrame:ToObjectSpace(part.CFrame)
			copy.Parent = model
		end
	end
	for _, part in model:GetDescendants() do
		if part:IsA("BasePart") then
			part.Anchored = true
			part.CanCollide = false
			part.CanQuery = false
			part.CanTouch = false
			part.CastShadow = false
			part.Massless = true
		end
	end
	model:ScaleTo(scale)
	model.Parent = cam()
	-- arms: built at the shrunk size, posed every frame (not part of the scaled model)
	local arms = nil
	if opts.arms then
		local a: ArmOptions = if type(opts.arms) == "table" then opts.arms else {}
		local folder = Instance.new("Model")
		folder.Name = "ViewmodelArms"
		folder.Parent = cam()
		arms = { folder = folder }
		for _, side in { "Right", "Left" } do
			local s = scale
			arms[side] = {
				arm = block(
					side .. "Arm",
					Vector3.new(0.55, 2.4, 0.55) * s,
					a.skin or skinColor(),
					Enum.Material.SmoothPlastic,
					folder
				),
				sleeve = block(
					side .. "Sleeve",
					Vector3.new(0.63, 1.6, 0.63) * s,
					a.sleeve or Color3.fromRGB(42, 47, 56),
					Enum.Material.Fabric,
					folder
				),
				glove = block(
					side .. "Glove",
					Vector3.new(0.6, 0.45, 0.6) * s,
					a.glove or Color3.fromRGB(24, 26, 30),
					Enum.Material.Fabric,
					folder
				),
			}
		end
	end
	local self = setmetatable({
		model = model,
		root = root,
		originals = originals,
		scale = scale,
		offset = opts.offset or DEFAULT_OFFSET,
		recoil = 0,
		back = opts.recoilBack or 0.45,
		pitch = opts.recoilPitch or 7,
		decay = opts.recoilDecay or 9,
		bindName = bindName,
		arms = arms,
		born = os.clock(),
		equipTime = if opts.equipTime ~= nil then opts.equipTime else 0.35,
		boltStart = nil :: number?,
		boltTime = 0.75,
	}, Viewmodel)
	-- the offset is authored at full size: positions shrink with the model, rotations do not
	local o = self.offset
	self.scaledOffset = CFrame.new(o.Position * scale) * o.Rotation
	RunService:BindToRenderStep(bindName, Enum.RenderPriority.Camera.Value + 1, function(dt: number)
		self:_step(dt)
	end)
	return self
end

-- one arm: the glove (hand) at `hand`, the arm reaching back toward `shoulder` (world space)
local function poseArm(parts: any, hand: Vector3, shoulder: Vector3, scale: number)
	local up = shoulder - hand
	if up.Magnitude < 1e-3 then
		return
	end
	up = up.Unit
	local right = up:Cross(Vector3.yAxis)
	if right.Magnitude < 1e-3 then
		right = Vector3.xAxis
	end
	right = right.Unit
	local back = right:Cross(up)
	local function at(dist: number): CFrame
		local p = hand + up * dist * scale
		return CFrame.fromMatrix(p, right, up, back)
	end
	parts.glove.CFrame = at(0.1)
	parts.arm.CFrame = at(1.2)
	parts.sleeve.CFrame = at(2.0)
end

function Viewmodel._step(self: any, dt: number)
	local camera = cam()
	if not camera then
		return
	end
	if self.model.Parent ~= camera then
		self.model.Parent = camera -- the camera object is replaced on respawn
		if self.arms then
			self.arms.folder.Parent = camera
		end
	end
	for _, part in self.originals do
		part.LocalTransparencyModifier = 1 -- the real tool is for other players' screens
	end
	self.recoil *= math.exp(-dt * self.decay)
	local r = self.recoil
	local s = self.scale
	local kick = CFrame.new(0, 0, self.back * s * r) * CFrame.Angles(math.rad(self.pitch * r), 0, 0)
	-- equip: rise from below, rolled in, settling into place
	local pose = CFrame.identity
	if self.equipTime > 0 then
		local k = 1 - smooth((os.clock() - self.born) / self.equipTime)
		if k > 0 then
			pose = CFrame.new(0, -1.4 * s * k, 0.6 * s * k) * CFrame.Angles(-0.9 * k, 0.35 * k, 0.5 * k)
		end
	end
	-- bolt cycle: the gun rolls toward the hand while the right hand works the bolt
	local boltK = 0
	if self.boltStart then
		local t = (os.clock() - self.boltStart) / self.boltTime
		if t >= 1 then
			self.boltStart = nil
		else
			boltK = math.sin(t * math.pi) -- 0 -> 1 -> 0
			pose *= CFrame.Angles(0.06 * boltK, 0, -0.35 * boltK)
		end
	end
	self.model:PivotTo(camera.CFrame * kick * self.scaledOffset * pose)
	if self.arms then
		local rootCF = self.root.CFrame
		local function anchor(name: string, fallback: Vector3): Vector3
			local att = self.root:FindFirstChild(name)
			return if att and att:IsA("Attachment") then att.WorldPosition else rootCF:PointToWorldSpace(fallback * s)
		end
		local grip = anchor("Grip", Vector3.zero)
		local support = anchor("Support", Vector3.new(0, 0.3, -1.6))
		local rightHand = grip
		if boltK > 0 then
			local knob = anchor("Bolt", Vector3.new(0.4, 0.5, -0.4))
			-- reach the knob, pull it back (along the gun), push it home
			local pull = rootCF.LookVector * -0.35 * s * math.clamp((boltK - 0.5) * 2, 0, 1)
			rightHand = grip:Lerp(knob + pull, math.clamp(boltK * 1.6, 0, 1))
		end
		local camCF = camera.CFrame
		local base = self.offset.Position
		poseArm(self.arms.Right, rightHand, camCF:PointToWorldSpace((base + SHOULDER.Right) * s), s)
		poseArm(self.arms.Left, support, camCF:PointToWorldSpace((base + SHOULDER.Left) * s), s)
	end
end

function Viewmodel.kick(self: any, amount: number?)
	self.recoil = math.min(1.5, self.recoil + (amount or 1))
end

function Viewmodel.bolt(self: any, duration: number?)
	self.boltTime = duration or 0.75
	self.boltStart = os.clock()
end

-- world position of an anchor (Attachment on the handle, from a.anchor in the build script) on the copy
function Viewmodel.point(self: any, anchor: string): Vector3?
	local att = self.root:FindFirstChild(anchor)
	if att and att:IsA("Attachment") then
		return att.WorldPosition
	end
	return nil
end

function Viewmodel.destroy(self: any)
	RunService:UnbindFromRenderStep(self.bindName)
	for _, part in self.originals do
		if part.Parent then
			part.LocalTransparencyModifier = 0
		end
	end
	self.model:Destroy()
	if self.arms then
		self.arms.folder:Destroy()
	end
end

return Viewmodel

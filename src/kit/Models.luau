-- Models (ReplicatedStorage.kit.Models) — spawn a kit-built 3D asset in game, PBR maps and all. MAY YIELD.
--   Models.spawn("crate", { cframe = CFrame.new(0, 3, 0), anchored = true }) -> Model (PrimaryPart "Root")
--   Models.tool("orbital_sniper", "Designator")                              -> Tool (Handle = the grip point)
--   model.Root.Muzzle (Attachment)  — every a.anchor("Muzzle", ...) in the build script, on Root / Handle
--   Models.has("crate")                                                       -> built + compiled?
--   Models.pose(model, "Slide", 0.25)  — move a jointed part (a.joint in the build script): studs or degrees
--   Models.play(model, "Cock and fire", { onMark = function(name) ... end }) -> handle  — the model's OWN MOTION:
--     an action cycle of the build script (a.cycle) played on the spawned model's joints, as the build checked it;
--     handle:Stop(); Models.cycles("revolver") -> the names. { loop = true, speed = 2 } as said
--   every joint is a Motor6D named after it (Root.Slide / Handle.Slide): the Animation Editor animates it too
-- Source: ReplicatedStorage.KitModels.<asset> (src/models/*.model.json, written by `kit asset` / `kit upload`).
-- Why not just set MeshId + a SurfaceAppearance in code? A game script cannot write SurfaceAppearance maps
-- (Plugin capability) and nothing can write MeshPart.MeshId — both measured in Studio. So each mesh comes from
-- AssetService:CreateMeshPartAsync (cached per id) and gets a CLONE of the SurfaceAppearance Rojo already filled.
-- The model's origin is the asset's Roblox origin (0,0,0 in the build script): for handheld items that is the
-- grip, so a Tool needs no hand-tuned Grip offsets. A group that is not uploaded yet spawns as a grey stand-in
-- of the right size (and warns once), so gameplay keeps working while assets are in moderation.
-- Each mesh is created with the COLLISION SHAPE and LEVEL OF DETAIL its build chose (the group's CollisionFidelity
-- / RenderFidelity attributes; a Tool's parts, which nothing touches, ask for a box). A mesh that fails to load is tried
-- again after a pause, a few times (ModelRules, spec'd), on its own: the spawns in between get the stand-in, and
-- when a later try loads the mesh every stand-in still in the world is SWAPPED for it in place - its look,
-- attributes, children and the joints that hold it moved over (seen in Studio 2026-11-17, card fbvv: a welded part
-- and a hinged one, grey to mesh, nothing moved, the hinge still turning its part). Seen in Studio (2026-11-17):
-- Roblox takes the two settings in CreateMeshPartAsync's options exactly as asked; if it refuses them the mesh is
-- created without.
local AssetService = game:GetService("AssetService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local ModelRules = require(script.Parent.ModelRules)

local Models = {}

export type SpawnOptions = {
	cframe: CFrame?, -- where the asset origin goes (default: world origin)
	anchored: boolean?, -- default false (welded to Root; anchor Root to pin it)
	collide: boolean?, -- default true for props; tools never collide
	ghost: boolean?, -- nothing will collide with, raycast or touch its parts (Models.tool): the cheapest shapes
	parent: Instance?, -- default: not parented (you parent it)
}

local templates: { [string]: MeshPart } = {}
local failures: { [string]: ModelRules.Failure } = {} -- a mesh that failed to load: tried again later (ModelRules)
local refused: { [string]: number } = {} -- times Roblox created a mesh only WITHOUT its settings
local inflight: { [string]: boolean } = {}
local warned: { [string]: boolean } = {}

local function folderFor(name: string): Instance?
	local root = ReplicatedStorage:FindFirstChild("KitModels")
	return root and root:FindFirstChild(name)
end

-- one CreateMeshPartAsync per mesh id and pair of settings: later spawns clone the template (fast, no web
-- request). collision / render are Roblox's own names (ModelRules.fidelity): a MeshPart's collision shape and
-- level of detail are fixed when it is created, so they are asked for here. A load that fails is NOT kept as
-- failed for the session: it is tried again after a pause (ModelRules.RETRY), a few times, then given up - in
-- between, and after, the caller gets nil at once (a stand-in), never a wait.
-- the grey stand-ins spawned while a mesh was failing to load, by its key: SWAPPED for the mesh when a later try loads
-- it (card fbvv: a stand-in stayed grey for the rest of the session), each with what the spawn gave it
local pendingStandIns: { [string]: { { part: BasePart, look: Instance? } } } = {}

-- the mesh's creation (the kit's own Studio playtest replaces it to make a load fail, then succeed)
Models._create = function(meshId: string, options: { [string]: any }?): MeshPart
	if options then
		return AssetService:CreateMeshPartAsync(Content.fromUri(meshId), options)
	end
	return AssetService:CreateMeshPartAsync(Content.fromUri(meshId))
end

-- every stand-in still in the world for this key becomes the loaded mesh: the same name, size, place, collisions,
-- transparency, attributes and look; its children (welds, motors, attachments) move over and every joint that held
-- the stand-in holds the mesh. -> how many were swapped
local function swapStandIns(key: string, template: MeshPart): number
	local list = pendingStandIns[key]
	pendingStandIns[key] = nil
	local swapped = 0
	for _, item in (list or {}) :: { { part: BasePart, look: Instance? } } do
		local old = item.part
		local holder = old.Parent
		if not holder then
			continue
		end
		local new = template:Clone()
		new.Name, new.Size, new.CFrame = old.Name, old.Size, old.CFrame
		new.Anchored, new.CanCollide, new.CanQuery, new.CanTouch =
			old.Anchored, old.CanCollide, old.CanQuery, old.CanTouch
		new.Massless, new.Transparency = old.Massless, old.Transparency
		new.CustomPhysicalProperties = old.CustomPhysicalProperties
		for k, v in old:GetAttributes() do
			new:SetAttribute(k, v)
		end
		if item.look then
			item.look:Clone().Parent = new
		end
		-- every joint that holds the stand-in holds the mesh: asked BEFORE its children move (a weld it carries is
		-- one of them - moved first, it was out of the model when the joints were asked, and the part fell)
		local top = holder:FindFirstAncestorWhichIsA("Model") or holder
		for _, d in top:GetDescendants() do
			if d:IsA("JointInstance") or d:IsA("WeldConstraint") or d:IsA("NoCollisionConstraint") then
				local j = d :: any
				if j.Part0 == old then
					j.Part0 = new
				end
				if j.Part1 == old then
					j.Part1 = new
				end
			end
		end
		for _, c in old:GetChildren() do
			c.Parent = new
		end
		new.Parent = holder
		if holder:IsA("Model") and (holder :: Model).PrimaryPart == old then
			(holder :: Model).PrimaryPart = new
		end
		old:Destroy()
		swapped += 1
	end
	return swapped
end

local function meshPart(meshId: string, collision: string, render: string): MeshPart?
	local key = ModelRules.key(meshId, collision, render)
	while inflight[key] do
		task.wait()
	end
	local cached = templates[key]
	if cached then
		return cached:Clone()
	end
	if not ModelRules.mayTry(failures[key], os.clock()) then
		return nil
	end
	inflight[key] = true
	local ok, part = pcall(function()
		return Models._create(meshId, {
			CollisionFidelity = (Enum.CollisionFidelity :: any)[collision],
			RenderFidelity = (Enum.RenderFidelity :: any)[render],
		})
	end)
	if not (ok and part) then
		-- the mesh itself may be fine and the settings refused: once more without them (Roblox's defaults). That
		-- part serves THIS spawn only - the next spawn asks for the settings again (the failure may have been the
		-- web request) - until it has happened ModelRules.REFUSALS times: then it is Roblox's answer, and kept
		local why = part
		ok, part = pcall(function()
			return Models._create(meshId, nil)
		end)
		if ok and part then
			refused[key] = (refused[key] or 0) + 1
			if refused[key] < ModelRules.REFUSALS then
				inflight[key] = nil
				return part
			end
			warn(`[Models] mesh {meshId} is created without {collision} / {render} this session (refused: {why})`)
		end
	end
	inflight[key] = nil
	if ok and part then
		templates[key] = part
		failures[key] = nil
		if pendingStandIns[key] then -- (the stand-ins spawned while it was failing: the mesh now)
			task.defer(swapStandIns, key, part :: MeshPart)
		end
		return (part :: MeshPart):Clone()
	end
	local state = ModelRules.failed(failures[key], os.clock())
	failures[key] = state
	if ModelRules.givenUp(state) then
		warn(`[Models] mesh {meshId} failed to load {state.fails} times, given up for this session: {part}`)
		pendingStandIns[key] = nil
	else
		local wait_ = ModelRules.RETRY[state.fails]
		warn(`[Models] mesh {meshId} failed to load, tried again in {wait_} s: {part}`)
		-- tried again on its own, not only when the next spawn asks: the stand-ins in the world are swapped then
		task.delay(wait_ + 0.05, function()
			if (templates[key] :: MeshPart?) == nil and pendingStandIns[key] then
				local got = meshPart(meshId, collision, render)
				if got then
					got:Destroy()
				end
			end
		end)
	end
	return nil
end

local function standIn(size: Vector3): BasePart
	local p = Instance.new("Part")
	p.Size = size
	p.Color = Color3.fromRGB(120, 124, 132)
	p.Material = Enum.Material.SmoothPlastic
	return p
end

function Models.has(name: string): boolean
	return folderFor(name) ~= nil
end

-- BREAK a part that was broken beforehand (a.fracture in its build script): the whole goes, its pieces show,
-- come loose and are pushed away from where the whole stood. `part`: the build's name of the broken part (nil: every
-- one the model has). opts.speed: studs a second (12); opts.collide: the pieces collide (true).
-- -> the pieces let go (the caller owns them: Debris, a fade, a pool). Nothing to break: an empty list.
function Models.shatter(model: Instance, part: string?, opts: { speed: number?, collide: boolean? }?): { BasePart }
	local speed = if opts and opts.speed then opts.speed else 12
	local collide = not (opts and opts.collide == false)
	local centres: { [string]: Vector3 } = {} -- (each whole's own: two broken parts each burst from their place)
	for _, child in model:GetChildren() do
		local whole = child:GetAttribute("Whole")
		if child:IsA("BasePart") and type(whole) == "string" and (part == nil or whole == part) then
			centres[whole] = centres[whole] or child.Position
			child.Transparency = 1
			child.CanCollide = false
			child.CanQuery = false
			child.CanTouch = false
		end
	end
	local out: { BasePart } = {}
	for _, child in model:GetChildren() do
		local shard = child:GetAttribute("Shard")
		if child:IsA("BasePart") and type(shard) == "string" and (part == nil or shard == part) then
			local was = child:GetAttribute("ShardTransparency")
			child.Transparency = if type(was) == "number" then was else 0
			child.CanCollide = collide
			child.CanQuery = true
			child.CanTouch = true
			child.Massless = false
			-- EVERY joint that holds the piece lets go: its welds, and a Motor6D it hangs on (a piece of a moving
			-- part - parented to the part it hangs from, it was kept, and the piece never fell: card q2k3)
			for _, joint in model:GetDescendants() do
				if joint:IsA("WeldConstraint") or joint:IsA("JointInstance") then
					local j = joint :: any
					if j.Part0 == child or j.Part1 == child then
						joint:Destroy()
					end
				end
			end
			local c = centres[shard] or child.Position
			local at = child.Position
			local vx, vy, vz = ModelRules.burst(c.X, c.Y, c.Z, at.X, at.Y, at.Z, speed)
			child.AssemblyLinearVelocity = Vector3.new(vx, vy, vz)
			child:SetAttribute("Shard", nil) -- (let go: a second shatter leaves it alone)
			table.insert(out, child)
		end
	end
	return out
end

function Models.spawn(name: string, options: SpawnOptions?): Model
	local opts: SpawnOptions = options or {}
	local folder = folderFor(name)
	assert(folder, `[Models] no KitModels.{name} — build it (lune run kit asset {name}) and let Rojo sync`)
	local model = Instance.new("Model")
	model.Name = name
	model:SetAttribute("KitAsset", name) -- (what Models.play looks the model's cycles up by; a Tool keeps it too)
	-- the far stand-in the build asked for (a.far): Roblox draws a StreamingMesh model as one coarse mesh while
	-- it is streamed out (a place with streaming on; elsewhere the setting does nothing)
	local far = ModelRules.far(folder:GetAttribute("Far"))
	if far then
		(model :: any).LevelOfDetail = (Enum.ModelLevelOfDetail :: any)[far] -- (not in the type definitions yet)
	end
	local root = Instance.new("Part")
	root.Name = "Root"
	root.Size = Vector3.new(0.2, 0.2, 0.2)
	root.Transparency = 1
	root.CanCollide = false
	root.CanQuery = false
	root.CanTouch = false
	root.Massless = true
	root.Anchored = opts.anchored == true
	root.CFrame = CFrame.identity
	root.Parent = model
	model.PrimaryPart = root
	-- anchors from the build script (a.anchor("Muzzle", ...)) -> Attachments on Root: Root.Muzzle.WorldPosition
	for key, value in folder:GetAttributes() do
		local anchor = string.match(key, "^Anchor_(.+)$")
		if anchor and typeof(value) == "Vector3" then
			local att = Instance.new("Attachment")
			att.Name = anchor
			att.Position = value
			att.Parent = root
		end
	end
	local collide = if opts.collide == nil then true else opts.collide
	local parts: { [string]: BasePart } = {}
	local jointed: { { group: Instance, part: BasePart } } = {}
	for _, group in folder:GetChildren() do
		local size = group:GetAttribute("Size")
		local center = group:GetAttribute("Center")
		local meshId = group:GetAttribute("MeshId")
		if typeof(size) ~= "Vector3" or typeof(center) ~= "Vector3" then
			continue
		end
		local part: BasePart? = nil
		local pendingKey: string? = nil
		if type(meshId) == "string" and meshId ~= "" then
			local collision, render = ModelRules.fidelity(
				group:GetAttribute("CollisionFidelity"),
				group:GetAttribute("RenderFidelity"),
				opts.ghost == true and not collide
			)
			part = meshPart(meshId, collision, render)
			if not part then -- (noted: if a later try loads it, this stand-in becomes the mesh - swapStandIns)
				pendingKey = ModelRules.key(meshId, collision, render)
			end
		end
		if part then
			local look = group:FindFirstChildOfClass("SurfaceAppearance")
			if look then
				look:Clone().Parent = part
			end
		else
			if not warned[name .. group.Name] then
				warned[name .. group.Name] = true
				if type(meshId) == "string" and meshId ~= "" then
					warn(`[Models] {name}/{group.Name} did not load — grey stand-in for this spawn`)
				else
					warn(
						`[Models] {name}/{group.Name} is not uploaded yet — grey stand-in (run: lune run kit upload)`
					)
				end
			end
			local stand = standIn(size)
			part = stand
			if pendingKey and not ModelRules.givenUp(failures[pendingKey]) then
				local list = pendingStandIns[pendingKey] or {}
				table.insert(list, { part = stand, look = group:FindFirstChildOfClass("SurfaceAppearance") })
				pendingStandIns[pendingKey] = list
			end
		end
		local p = part :: BasePart
		p.Name = group.Name
		p.Size = size
		local transparency = group:GetAttribute("Transparency")
		if type(transparency) == "number" and transparency > 0 then
			p.Transparency = transparency
		end
		p.CFrame = CFrame.new(center)
		p.Anchored = false
		p.CanCollide = collide
		p.Massless = true
		-- the group's physics material (a.physics): how it slides and bounces. (Its density is carried too; a
		-- spawned model's parts are massless, so it tells only once a game makes a part heavy again.)
		local density, friction, elasticity = ModelRules.physics(
			group:GetAttribute("PhysDensity"),
			group:GetAttribute("PhysFriction"),
			group:GetAttribute("PhysElasticity")
		)
		if density and friction and elasticity then
			p.CustomPhysicalProperties = PhysicalProperties.new(density, friction, elasticity)
		end
		-- a part broken beforehand (a.fracture): the whole shows, its pieces wait hidden where they fit
		local shard, whole = group:GetAttribute("Shard"), group:GetAttribute("Whole")
		if type(shard) == "string" then
			p:SetAttribute("Shard", shard)
			p:SetAttribute("ShardTransparency", p.Transparency)
			p.Transparency = 1
			p.CanCollide = false
			p.CanQuery = false
			p.CanTouch = false
		elseif type(whole) == "string" then
			p:SetAttribute("Whole", whole)
		end
		parts[group.Name] = p
		if type(group:GetAttribute("Joint")) == "string" then
			table.insert(jointed, { group = group, part = p })
		else
			local weld = Instance.new("WeldConstraint")
			weld.Part0 = root
			weld.Part1 = p
			weld.Parent = p
		end
		p.Parent = model
	end
	-- moving parts: a Motor6D at the joint pivot whose X axis is the joint axis (Transform = the pose)
	for _, item in jointed do
		local g, p = item.group, item.part
		local parentName = g:GetAttribute("JointParent")
		local parent: BasePart = if type(parentName) == "string"
				and parentName ~= "main"
				and parts[parentName]
			then parts[parentName]
			else root
		if g:GetAttribute("JointKind") == "fixed" then
			local weld = Instance.new("WeldConstraint")
			weld.Part0 = parent
			weld.Part1 = p
			weld.Parent = p
			continue
		end
		local axis = (g:GetAttribute("JointAxis") :: Vector3).Unit
		local pivot = g:GetAttribute("JointPivot") :: Vector3
		local up = if math.abs(axis.Y) < 0.95 then Vector3.yAxis else Vector3.xAxis
		local z = axis:Cross(up).Unit
		local frame = CFrame.fromMatrix(pivot, axis, z:Cross(axis).Unit, z)
		local motor = Instance.new("Motor6D")
		motor.Name = g:GetAttribute("Joint") :: string
		motor.Part0 = parent
		motor.Part1 = p
		motor.C0 = parent.CFrame:ToObjectSpace(frame)
		motor.C1 = p.CFrame:ToObjectSpace(frame)
		motor:SetAttribute("Kind", g:GetAttribute("JointKind"))
		motor:SetAttribute("Min", g:GetAttribute("JointMin"))
		motor:SetAttribute("Max", g:GetAttribute("JointMax"))
		if type(g:GetAttribute("JointFollows")) == "string" then -- (a.couple: this joint follows another)
			motor:SetAttribute("Follows", g:GetAttribute("JointFollows"))
			model:SetAttribute("KitFollowers", true) -- (Models.pose looks for followers only on a model that has one)
			motor:SetAttribute("Ratio", g:GetAttribute("JointRatio"))
			motor:SetAttribute("Offset", g:GetAttribute("JointOffset"))
		end
		motor.Parent = parent
	end
	if opts.cframe then
		model:PivotTo(opts.cframe)
	end
	if opts.parent then
		model.Parent = opts.parent
	end
	return model
end

-- move a jointed part: value in studs (slide) or degrees (hinge), clamped to the joint's range
local function poseMotor(motor: Motor6D, value: number)
	local lo, hi = motor:GetAttribute("Min"), motor:GetAttribute("Max")
	if type(lo) == "number" and type(hi) == "number" then
		value = math.clamp(value, math.min(lo, hi), math.max(lo, hi))
	end
	if motor:GetAttribute("Kind") == "hinge" then
		motor.Transform = CFrame.Angles(math.rad(value), 0, 0)
	else
		motor.Transform = CFrame.new(value, 0, 0)
	end
end

function Models.pose(model: Instance, joint: string, value: number)
	local motor: Instance? = nil
	for _, d in model:GetDescendants() do -- (the Motor6D of that name: a mesh group may carry the same name)
		if d.Name == joint and d:IsA("Motor6D") then
			motor = d
			break
		end
	end
	assert(motor and motor:IsA("Motor6D"), `[Models] {model.Name} has no joint {joint}`)
	poseMotor(motor, value)
	if model:GetAttribute("KitFollowers") ~= true then
		return -- (no joint of this model follows another: nothing more to look for)
	end
	-- the joints that FOLLOW this one (a.couple), and theirs (four deep at most)
	local drivers: { [string]: number } = { [joint] = value }
	for _ = 1, 4 do
		local moved = false
		for _, d in model:GetDescendants() do
			local follows = d:IsA("Motor6D") and d:GetAttribute("Follows")
			if type(follows) == "string" and drivers[follows] ~= nil and drivers[d.Name] == nil then
				local v = ModelRules.follow(drivers[follows], d:GetAttribute("Ratio"), d:GetAttribute("Offset"))
				poseMotor(d :: Motor6D, v)
				drivers[d.Name] = v
				moved = true
			end
		end
		if not moved then
			break
		end
	end
end

-- A CHAIN OF JOINTS, POSED BY WHERE ITS TIP SHOULD BE (a.reach in the build script; ModelRules.reach). `target`: a
-- place in the WORLD (a Vector3) - or the name of a pose the build solved. The chain's joints are posed (and the
-- joints that follow them); -> how far the tip is left from the target, in studs (0 for a named pose).
-- No such chain, or no such named pose: an error that says which the model has.
local chainTables: { [string]: any } = {} -- (a chain decoded once an asset, as a cycle is)

local function chainOf(model: Instance, chain: string): any
	local asset = model:GetAttribute("KitAsset")
	local key = tostring(asset) .. "\0" .. chain
	if chainTables[key] then
		return chainTables[key]
	end
	local folder = if type(asset) == "string" then folderFor(asset) else nil
	local list = folder and folder:FindFirstChild("Chains")
	local value = list and list:FindFirstChild(chain)
	assert(value and value:IsA("StringValue"), `[Models] {model.Name} has no chain {chain}`)
	local ok, data = pcall(function()
		return HttpService:JSONDecode(value.Value)
	end)
	assert(
		ok and type(data) == "table" and type(data.joints) == "table",
		`[Models] {model.Name}'s chain {chain} cannot be read`
	)
	chainTables[key] = data
	return data
end

function Models.reach(model: Instance, chain: string, target: Vector3 | string): number
	local data = chainOf(model, chain)
	if type(target) == "string" then
		local pose = data.poses and data.poses[target]
		assert(type(pose) == "table", `[Models] {model.Name}'s chain {chain} has no pose {target}`)
		for _, j in data.joints do
			Models.pose(model, j.name, pose.values[j.name] or 0)
		end
		return 0
	end
	-- the place in the MODEL's own frame, at the size it was built: its root (a Tool's is its Handle), its scale
	local root = model:FindFirstChild("Root") or model:FindFirstChild("Handle")
	if not (root and root:IsA("BasePart")) and model:IsA("Model") then
		root = model.PrimaryPart
	end
	assert(root and root:IsA("BasePart"), `[Models] {model.Name} has no root part to reach from`)
	local scale = if model:IsA("Model") then model:GetScale() else 1
	local here = (root :: BasePart).CFrame:PointToObjectSpace(target) / math.max(scale, 1e-6)
	-- from the pose the chain is in now: it goes on from there, it does not jump to another way of folding
	local start: { number } = {}
	local motors: { [string]: Motor6D } = {}
	for _, d in model:GetDescendants() do
		if d:IsA("Motor6D") then
			motors[d.Name] = d
		end
	end
	for i, j in data.joints do
		local motor = motors[j.name]
		assert(motor, `[Models] {model.Name} has no joint {j.name} (its chain {chain} names it)`)
		if j.kind == "slide" then
			start[i] = motor.Transform.X
		else
			local x = motor.Transform:ToEulerAnglesXYZ()
			start[i] = math.deg(x)
		end
	end
	local values, miss = ModelRules.reach(data.joints, data.tip, { here.X, here.Y, here.Z }, start)
	for i, j in data.joints do
		Models.pose(model, j.name, values[i])
	end
	return miss * scale
end

-- A MODEL'S OWN MOTION (a.cycle in the build script; the table: kit/blender/rbx_cycleplay.py, the rule:
-- ModelRules.cycleAt): the names of an asset's action cycles, and one of them played on a spawned model's joints.
local cycleTables: { [string]: ModelRules.Cycle } = {}

local function cycleOf(asset: string, cycle: string): ModelRules.Cycle?
	local key = asset .. "\0" .. cycle
	local known = cycleTables[key]
	if known then
		return known
	end
	local folder = folderFor(asset)
	local list = folder and folder:FindFirstChild("Cycles")
	local value = list and list:FindFirstChild(cycle)
	if not (value and value:IsA("StringValue")) then
		return nil
	end
	local ok, decoded = pcall(function()
		return HttpService:JSONDecode(value.Value)
	end)
	if not ok or type(decoded) ~= "table" then
		return nil
	end
	cycleTables[key] = decoded
	return decoded
end

function Models.cycles(name: string): { string }
	local folder = folderFor(name)
	local list = folder and folder:FindFirstChild("Cycles")
	local names = {}
	local children: { Instance } = if list then list:GetChildren() else {}
	for _, child in children do
		table.insert(names, child.Name)
	end
	table.sort(names)
	return names
end

export type PlayOptions = {
	loop: boolean?, -- default: as the build script said (a.cycle(..., loop=True))
	speed: number?, -- default 1
	onMark: ((name: string) -> ())?, -- each mark of the cycle as it is passed ("fire", "cock")
	onDone: (() -> ())?, -- when a cycle that does not loop has played through (not when it was stopped)
	fade: number?, -- seconds: the cycle fades in from the pose the joints are in (default 0: it cuts to its start)
}
export type PlayHandle = { playing: boolean, Stop: (self: PlayHandle) -> () }

-- play one of the model's action cycles on its joints. The model is one Models.spawn / Models.tool made (it knows
-- its asset); the joints are posed every frame until the cycle ends, the handle is stopped, or the model has left
-- the game. EVERY moving joint is posed: one the cycle does not key stands at rest (as the build checked it). A
-- second play on the same model stops the first. Run it where the model is simulated: on the client for a held
-- tool, on the server for a world prop.
local playing: { [Instance]: PlayHandle } = setmetatable({}, { __mode = "k" }) :: any

function Models.play(model: Instance, cycle: string, options: PlayOptions?): PlayHandle
	local opts: PlayOptions = options or {}
	local asset = model:GetAttribute("KitAsset")
	assert(type(asset) == "string", `[Models] {model.Name} was not spawned by Models: it has no cycles`)
	local data = cycleOf(asset, cycle)
	assert(data, `[Models] {asset} has no cycle "{cycle}" (its cycles: {table.concat(Models.cycles(asset), ", ")})`)
	local loop = if opts.loop == nil then data.loop == true else opts.loop
	local speed = opts.speed or 1
	assert(speed > 0, `[Models] play: speed {speed} - over 0 (to hold a pose, use Models.pose)`)
	-- the model's own joints, found once: only Motor6Ds (a mesh group or an anchor may carry a joint's name)
	local motors: { [string]: Motor6D } = {}
	for _, d in model:GetDescendants() do
		if d:IsA("Motor6D") and d:GetAttribute("Kind") ~= nil then
			motors[d.Name] = d
		end
	end
	local old = playing[model]
	if old then
		old:Stop()
	end
	-- (a fade starts from where every joint stands NOW: whatever played before, a pose, or rest)
	local fade = opts.fade or 0
	assert(fade >= 0, `[Models] play: fade {fade} - seconds, 0 or more`)
	local from: { [string]: number }? = nil
	if fade > 0 then
		local stood: { [string]: number } = {}
		for name, motor in motors do
			if motor:GetAttribute("Kind") == "hinge" then
				local x = motor.Transform:ToEulerAnglesXYZ()
				stood[name] = math.deg(x)
			else
				stood[name] = motor.Transform.X
			end
		end
		from = stood
	end
	local faded = 0
	local handle = { playing = true } :: any
	local at: number? = nil
	local connection: RBXScriptConnection? = nil
	local wasInGame = model:IsDescendantOf(game)
	function handle.Stop(_self: any)
		handle.playing = false
		if connection then
			connection:Disconnect()
			connection = nil
		end
		if playing[model] == handle then
			playing[model] = nil
		end
	end
	local function step(dt: number)
		local s = ModelRules.playStep(data, at, dt, speed, loop)
		at = s.at
		local values = s.values
		if from then -- (fading in: real time, not the cycle's speed)
			faded += math.max(0, dt)
			values = ModelRules.blend(from, values, faded / fade)
			if faded >= fade then
				from = nil
			end
		end
		for joint, value in values do
			local motor = motors[joint]
			if motor then
				poseMotor(motor, value)
			end
		end
		if opts.onMark then
			for _, name in s.marks do
				task.spawn(opts.onMark, name)
			end
		end
		if s.done then
			handle:Stop()
			if opts.onDone then
				task.spawn(opts.onDone)
			end
		end
	end
	playing[model] = handle
	step(0)
	if handle.playing then
		connection = RunService.Heartbeat:Connect(function(dt: number)
			-- (a model not yet parented plays on - a Tool is made before it goes in a Backpack; one that WAS in
			-- the game and has left it is gone)
			local inGame = model:IsDescendantOf(game)
			if wasInGame and not inGame then
				handle:Stop()
				return
			end
			wasInGame = inGame
			step(dt)
		end)
	end
	return handle
end

-- a Tool whose Handle is the asset origin (the grip, for handheld builds): Tool.Grip stays identity unless you
-- want a different hold. Every mesh is weightless and non-colliding (a heavy rifle drags the character).
function Models.tool(name: string, toolName: string?): Tool
	local model = Models.spawn(name, { collide = false, ghost = true })
	local tool = Instance.new("Tool")
	tool.Name = toolName or name
	tool.RequiresHandle = true
	tool.CanBeDropped = false
	tool:SetAttribute("KitAsset", name)
	local root = model.PrimaryPart :: BasePart
	root.Name = "Handle"
	for _, child in model:GetChildren() do
		if child:IsA("BasePart") then
			child.CanQuery = false
			child.CanTouch = false
		end
		child.Parent = tool
	end
	model:Destroy()
	return tool
end

-- R6 OUTFITS: an asset built per body part (groups Torso, LeftArm, RightArm, LeftLeg, RightLeg — rbx_garment, the R6
-- body standing at the origin, its feet at y 0) worn on a character: each group welded to its limb at the offset it
-- had from that limb's rest place, so it moves with the limb. The preview body (group "mannequin") is dropped.
--   Models.wear(player.Character, "coat_hero") -> the outfit Model, parented to the character
local R6_REST: { [string]: { limb: string, rest: Vector3 } } = {
	Torso = { limb = "Torso", rest = Vector3.new(0, 3, 0) },
	LeftArm = { limb = "Left Arm", rest = Vector3.new(-1.5, 3, 0) },
	RightArm = { limb = "Right Arm", rest = Vector3.new(1.5, 3, 0) },
	LeftLeg = { limb = "Left Leg", rest = Vector3.new(-0.5, 1, 0) },
	RightLeg = { limb = "Right Leg", rest = Vector3.new(0.5, 1, 0) },
}

function Models.wear(character: Model, name: string): Model
	local outfit = Models.spawn(name, { collide = false })
	local torso = character:FindFirstChild("Torso")
	assert(torso and torso:IsA("BasePart"), `[Models] wear: {character.Name} has no Torso (an R6 character is needed)`)
	local preview = outfit:FindFirstChild("mannequin")
	if preview then
		preview:Destroy()
	end
	for group, spec in R6_REST do
		local part = outfit:FindFirstChild(group)
		local limb = character:FindFirstChild(spec.limb)
		if not (part and part:IsA("BasePart") and limb and limb:IsA("BasePart")) then
			continue
		end
		for _, w in part:GetChildren() do
			if w:IsA("WeldConstraint") then
				w:Destroy()
			end
		end
		local offset = CFrame.new(part.Position - spec.rest) -- its place relative to the limb, at rest
		part.CFrame = limb.CFrame * offset
		part.CanCollide = false
		part.CanQuery = false
		part.CanTouch = false
		part.Massless = true
		local weld = Instance.new("Weld")
		weld.Name = "Wear"
		weld.Part0 = limb
		weld.Part1 = part
		weld.C0 = offset
		weld.Parent = part
	end
	-- the outfit's Root (and anything welded to it) rides the torso: the model origin is the feet, 3 studs below it
	local root = outfit.PrimaryPart :: BasePart
	root.CFrame = torso.CFrame * CFrame.new(0, -3, 0)
	local rootWeld = Instance.new("Weld")
	rootWeld.Part0 = torso
	rootWeld.Part1 = root
	rootWeld.C0 = CFrame.new(0, -3, 0)
	rootWeld.Parent = root
	outfit.Parent = character
	return outfit
end

return Models

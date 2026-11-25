-- booth.luau — the VFX booth, run INSIDE Roblox Studio (edit mode, the kit's scratch place) through the shared capture
-- bridge (kit/tools/studio_capture.py, card 4s96): `lune run kit vfx booth <name>` writes the run's script
-- (<run>.studio.luau: the job - views, moments, time scale, the preset as written + the parts it uses, the textures
-- it names - inside it) and this file is installed once into ServerStorage.KitStudioBridge.VfxBooth. Nothing is
-- fetched: the kit's VfxStage / VfxCompose are a fresh copy of the place's own src/kit (ReplicatedStorage.kit; a
-- place older than the repo is NAMED in the answer), the presentation clip is the place's KitAnimations.<clip>. It
-- builds a stage (golden-hour light, bloom, haze, a long floor with rocks and pillars down range, a sword-holding
-- stand-in whose swing follows the effect clock) and, per camera view, plays the effect, freezes it at every moment
-- and SIGNALS each held frame with a colour over the 3D view (kit/studio/capture_bridge.luau) for the capture
-- (python kit/vfx/capture.py studio) to read the window. The run's answer (every picture's view, moment and clock)
-- is kept for <run>.collect.luau. Nothing is uploaded, nothing in the place outside KitVfxBooth* is touched except
-- Lighting effects named KitBooth*, the overcast sky's Terrain.KitBoothClouds and the camera. The light is one of the
-- player's four judging skies (job.sky: night / day / overcast / sunset - SKIES below).
-- Module form: { run(jobJson) -> JSON line, replay(view) }; calling it as before, (nil, view), replays.
local Lighting = game:GetService("Lighting")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local Bridge = (require :: any)(script.Parent:WaitForChild("Bridge")) -- kit/studio/capture_bridge.luau

local function part(props: { [string]: any }, parent: Instance): Part
	local p = Instance.new("Part")
	p.Anchored = true
	p.CanCollide = false
	p.CastShadow = true
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	for k, v in props do
		(p :: any)[k] = v
	end
	p.Parent = parent
	return p
end

-- the four judging skies, the SAME names as the browser player's (kit/vfx/player/player.js SKIES; booth.sky or
-- `kit vfx booth <name> --sky <sky>`), so kit/vfx/calibrate.py can measure the player against Roblox under each one
-- (LIMITATIONS_FIXES_V4 13.3.1: "Daylight / Overcast / Sunset / Night"). night = the booth's original dusk arena (the
-- light the 2026-10-10 calibration was made in: unchanged); day / overcast / sunset follow the player's sky of that
-- name (its fog colour is the Atmosphere's Color, its sun the Brightness and clock). The Roblox side is the truth: the
-- player is fitted to these, never the other way round
local SKIES: { [string]: { [string]: any } } = {
	night = {
		clock = 18.55,
		sun = 1.6,
		exposure = -0.15,
		ambient = { 34, 32, 44 },
		outdoor = { 82, 74, 92 },
		atmo = {
			density = 0.36,
			offset = 0.15,
			color = { 196, 156, 132 },
			decay = { 92, 72, 112 },
			glare = 0.5,
			haze = 1.8,
		},
	},
	day = {
		clock = 14,
		sun = 3,
		exposure = 0,
		ambient = { 70, 72, 82 },
		outdoor = { 128, 130, 142 },
		atmo = {
			density = 0.3,
			offset = 0.25,
			color = { 188, 216, 242 },
			decay = { 106, 140, 190 },
			glare = 0,
			haze = 1,
		},
	},
	overcast = {
		clock = 12,
		sun = 1,
		exposure = 0,
		ambient = { 110, 112, 116 },
		outdoor = { 150, 152, 156 },
		atmo = {
			density = 0.45,
			offset = 0.1,
			color = { 169, 173, 179 },
			decay = { 120, 124, 130 },
			glare = 0,
			haze = 2.5,
		},
		clouds = 0.92,
	},
	sunset = {
		clock = 17.9,
		sun = 2.2,
		exposure = 0,
		ambient = { 60, 44, 46 },
		outdoor = { 120, 86, 80 },
		atmo = {
			density = 0.4,
			offset = 0.2,
			color = { 201, 138, 98 },
			decay = { 106, 82, 112 },
			glare = 0.6,
			haze = 2,
		},
	},
}

local function skyRgb(c: { number }): Color3
	return Color3.fromRGB(c[1], c[2], c[3])
end

local function setLighting(job: any)
	pcall(function()
		(Lighting :: any).Technology = Enum.Technology.Future
	end)
	-- the sky: job.sky (--sky), else the preset's booth.sky, else night (the original dusk arena); job.clock / sun /
	-- exposure still override one number of it
	local K = SKIES[job.sky or ""] or SKIES.night
	Lighting.ClockTime = job.clock or K.clock
	Lighting.Brightness = job.sun or K.sun
	Lighting.ExposureCompensation = job.exposure or K.exposure
	Lighting.Ambient = skyRgb(K.ambient)
	Lighting.OutdoorAmbient = skyRgb(K.outdoor)
	Lighting.EnvironmentDiffuseScale = 0.6
	Lighting.EnvironmentSpecularScale = 0.6
	local bloom = Lighting:FindFirstChildOfClass("BloomEffect") or Instance.new("BloomEffect")
	bloom.Intensity = (job.bloom and job.bloom.intensity) or 0.9
	bloom.Size = (job.bloom and job.bloom.size) or 36
	bloom.Threshold = (job.bloom and job.bloom.threshold) or 1.0
	bloom.Parent = Lighting
	local atmo = Lighting:FindFirstChildOfClass("Atmosphere") or Instance.new("Atmosphere")
	atmo.Density = K.atmo.density
	atmo.Offset = K.atmo.offset
	atmo.Color = skyRgb(K.atmo.color)
	atmo.Decay = skyRgb(K.atmo.decay)
	atmo.Glare = K.atmo.glare
	atmo.Haze = K.atmo.haze
	atmo.Parent = Lighting
	-- overcast's cloud deck (Workspace.Terrain.Clouds, named KitBoothClouds); any other sky takes it away again
	local clouds = Workspace.Terrain:FindFirstChild("KitBoothClouds")
	if K.clouds then
		if not clouds then
			clouds = Instance.new("Clouds")
			clouds.Name = "KitBoothClouds"
			clouds.Parent = Workspace.Terrain
		end
		(clouds :: any).Cover = K.clouds;
		(clouds :: any).Density = 0.8
	elseif clouds then
		clouds:Destroy()
	end
	for _, e in Lighting:GetChildren() do
		if e.Name == "KitVfxStage" or e.Name == "KitVfxImpact" then
			e:Destroy() -- left over from an interrupted run
		end
	end
end

local function buildArena(root: Instance)
	local placeFloor = Workspace:FindFirstChild("BoothFloor") -- the booth place's own plate: our floor replaces it
	if placeFloor and placeFloor:IsA("BasePart") then
		placeFloor.Transparency = 1
	end
	part({
		Name = "Floor",
		Size = Vector3.new(900, 2, 900),
		CFrame = CFrame.new(0, -1, -200),
		Color = Color3.fromRGB(150, 128, 102),
		Material = Enum.Material.Ground,
	}, root)
	local r = Random.new(7)
	for i = 1, 26 do
		local z = -r:NextNumber(30, 330)
		local x = r:NextNumber(26, 70) * (if i % 2 == 0 then 1 else -1)
		local s = r:NextNumber(3, 9)
		part({
			Name = "Rock",
			Size = Vector3.new(s, s * r:NextNumber(0.5, 1.2), s * r:NextNumber(0.7, 1.3)),
			CFrame = CFrame.new(x, s * 0.3, z)
				* CFrame.Angles(r:NextNumber(-0.3, 0.3), r:NextNumber(0, 6), r:NextNumber(-0.3, 0.3)),
			Color = Color3.fromRGB(118, 104, 92),
			Material = Enum.Material.Slate,
		}, root)
	end
	for i = 1, 6 do
		local z = -70 - i * 38
		for _, side in { -1, 1 } do
			part({
				Name = "Pillar",
				Size = Vector3.new(5, 26 + i * 2, 5),
				CFrame = CFrame.new(side * (34 + i * 3), (26 + i * 2) / 2, z),
				Color = Color3.fromRGB(176, 162, 140),
				Material = Enum.Material.Limestone,
			}, root)
		end
	end
	-- the target: a dummy and a wall where the beam lands
	part({
		Name = "TargetWall",
		Size = Vector3.new(70, 30, 8),
		CFrame = CFrame.new(0, 15, -300),
		Color = Color3.fromRGB(140, 126, 110),
		Material = Enum.Material.Cobblestone,
	}, root)
end

local function rgb(v: any, default: Color3): Color3
	if type(v) == "table" and type(v[1]) == "number" and type(v[2]) == "number" and type(v[3]) == "number" then
		return Color3.fromRGB(v[1], v[2], v[3])
	end
	return default
end

-- G2, THE 2-FIGHTER SCENE (job.scene = kit/vfx/scenes/<name>.json, LIMITATIONS_FIXES_V4 3.4 step 1: the 24-stud arena
-- the player is calibrated in): the SAME layout the browser player builds from the same file (player.js buildScene) -
-- the ground, the scene's floor plate + curb in place of the down-range set, and its victim: Roblox's own R6
-- character, anchored, facing the attacker (the actor on the origin). -> the scene's anchors: "victim" the victim's
-- model (highlight layers), "victim<Name>" an attachment at each of the scene's points
local function buildScene(root: Instance, sc: any): { [string]: Instance }
	local placeFloor = Workspace:FindFirstChild("BoothFloor")
	if placeFloor and placeFloor:IsA("BasePart") then
		placeFloor.Transparency = 1
	end
	local a = sc.arena or {}
	local size = tonumber(a.size) or 24
	local c = if type(a.center) == "table" then a.center else { 0, 0, 0 }
	part({
		Name = "Floor",
		Size = Vector3.new(900, 2, 900),
		CFrame = CFrame.new(0, -1, -200),
		Color = Color3.fromRGB(150, 128, 102),
		Material = Enum.Material.Ground,
	}, root)
	local okMat, floorMat = pcall(function()
		return (Enum.Material :: any)[(a.floor or {}).material or "Slate"]
	end)
	part({
		Name = "ArenaFloor",
		Size = Vector3.new(size, 0.2, size),
		CFrame = CFrame.new(c[1], -0.08, c[3]), -- its top 0.02 above the ground, like the player's plate
		Color = rgb((a.floor or {}).color, Color3.fromRGB(118, 112, 104)),
		Material = if okMat and floorMat then floorMat else Enum.Material.Slate,
	}, root)
	local curb = a.curb or {}
	local ch, cw = tonumber(curb.height) or 0, tonumber(curb.width) or 0
	if ch > 0 and cw > 0 then
		for _, b in
			{
				{ size, cw, 0, -(size - cw) / 2 },
				{ size, cw, 0, (size - cw) / 2 },
				{ cw, size - 2 * cw, -(size - cw) / 2, 0 },
				{ cw, size - 2 * cw, (size - cw) / 2, 0 },
			}
		do
			part({
				Name = "Curb",
				Size = Vector3.new(b[1], ch, b[2]),
				CFrame = CFrame.new(c[1] + b[3], ch / 2, c[3] + b[4]),
				Color = rgb(a.curbColor, Color3.fromRGB(86, 80, 74)),
				Material = Enum.Material.Concrete,
			}, root)
		end
	end
	local anchors: { [string]: Instance } = {}
	local victim = nil
	for _, f in sc.fighters or {} do
		if type(f) == "table" and f.role == "victim" then
			victim = f
		end
	end
	if victim then
		local Players = game:GetService("Players")
		local desc = Instance.new("HumanoidDescription")
		local col = victim.colors or {}
		local body, torso, skin =
			rgb(col.body, Color3.fromRGB(92, 42, 38)),
			rgb(col.torso, Color3.fromRGB(150, 146, 138)),
			rgb(col.head, Color3.fromRGB(240, 214, 190))
		desc.HeadColor = skin
		desc.TorsoColor = torso
		desc.LeftArmColor = body
		desc.RightArmColor = body
		desc.LeftLegColor = body
		desc.RightLegColor = body
		local model = Players:CreateHumanoidModelFromDescription(desc, Enum.HumanoidRigType.R6)
		model.Name = "Victim"
		for _, d in model:GetDescendants() do
			if d:IsA("BasePart") then
				d.Anchored = true
				d.CanCollide = false
				d.CastShadow = true
			end
		end
		local p, fc = victim.pos, victim.face or { 0, 0, 1 }
		-- an R6's root sits 3 studs up (legs 2 + half the torso); the model's forward is -Z, like the actor's
		model:PivotTo(CFrame.new(p[1], p[2] + 3, p[3]) * CFrame.Angles(0, math.atan2(-fc[1], -fc[3]), 0))
		model.Parent = root
		anchors.victim = model
		local holder = model:FindFirstChild("Torso") or model:FindFirstChild("HumanoidRootPart")
		if holder and holder:IsA("BasePart") then
			for k, v in sc.anchors or {} do
				if type(k) == "string" and k ~= "victim" and type(v) == "table" then
					local att = Instance.new("Attachment")
					att.Name = k
					att.Parent = holder
					-- world-aligned like the player's scene anchors (a fixed point, no turn): "Back" is +Z in both
					att.WorldCFrame = CFrame.new(v[1], v[2], v[3])
					anchors[k] = att
				end
			end
		end
	end
	return anchors
end

-- the actor: Roblox's own R15 character (CreateHumanoidModelFromDescription, edit-mode safe), parts anchored and
-- posed by forward kinematics over its rig attachments (child = parent * a0 * rotation * a1^-1), a sword in the
-- right hand (blade runs out past the fist along the hand's -Y). pose(t) plays the move on the effect clock:
-- a low guard, the raise to an overhead two-handed hold, the chop. Anchors: blade, bladeMid, tip, hilt.
local function buildActor(root: Instance, job: any): ({ [string]: Instance }, (t: number) -> ())
	local Players = game:GetService("Players")
	local desc = Instance.new("HumanoidDescription")
	local cloth, armor, skin = Color3.fromRGB(38, 58, 140), Color3.fromRGB(196, 200, 210), Color3.fromRGB(240, 214, 190)
	desc.HeadColor = skin
	desc.TorsoColor = armor
	desc.LeftArmColor = cloth
	desc.RightArmColor = cloth
	desc.LeftLegColor = cloth
	desc.RightLegColor = cloth
	local model = Players:CreateHumanoidModelFromDescription(desc, Enum.HumanoidRigType.R15)
	model.Name = "Actor"
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") then
			d.Anchored = true
			d.CanCollide = false
			d.CastShadow = true
		elseif d:IsA("LuaSourceContainer") then
			d:Destroy()
		end
	end
	local hum = model:FindFirstChildOfClass("Humanoid")
	if hum then
		hum.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
		hum.HealthDisplayType = Enum.HumanoidHealthDisplayType.AlwaysOff
	end
	model.Parent = root
	type Joint = { parent: BasePart, child: BasePart, a0: Attachment, a1: Attachment }
	local joints: { [string]: Joint } = {}
	for _, ac in model:GetDescendants() do
		if ac:IsA("AnimationConstraint") and ac.Attachment0 and ac.Attachment1 then
			local a0, a1 = ac.Attachment0 :: Attachment, ac.Attachment1 :: Attachment
			joints[ac.Name] = { parent = a0.Parent :: BasePart, child = a1.Parent :: BasePart, a0 = a0, a1 = a1 }
		end
	end
	local order = {
		"Root",
		"Waist",
		"Neck",
		"LeftShoulder",
		"LeftElbow",
		"LeftWrist",
		"RightShoulder",
		"RightElbow",
		"RightWrist",
		"LeftHip",
		"LeftKnee",
		"LeftAnkle",
		"RightHip",
		"RightKnee",
		"RightAnkle",
	}
	local hrp = model:FindFirstChild("HumanoidRootPart") :: BasePart
	local hand = model:FindFirstChild("RightHand") :: BasePart
	-- the sword
	local sword = Instance.new("Model")
	sword.Name = "Sword"
	sword.Parent = root
	local guard = part({
		Name = "Guard",
		Size = Vector3.new(1.3, 0.22, 0.3),
		Color = Color3.fromRGB(220, 180, 70),
		Material = Enum.Material.Metal,
	}, sword)
	local grip =
		part({ Name = "Grip", Size = Vector3.new(0.24, 0.9, 0.24), Color = Color3.fromRGB(40, 60, 150) }, sword)
	local blade = part({
		Name = "Blade",
		Size = Vector3.new(0.34, 4.6, 0.09),
		Color = Color3.fromRGB(226, 230, 240),
		Material = Enum.Material.Metal,
		Reflectance = 0.2,
	}, sword)
	local function att(name: string, y: number): Attachment
		local a = Instance.new("Attachment")
		a.Name = name
		a.Position = Vector3.new(0, y, 0)
		a.Parent = blade
		return a
	end
	local anchors: { [string]: Instance } = {
		body = model, -- the whole character (highlight layers)
		blade = blade,
		bladeMid = att("Mid", 0),
		tip = att("Tip", -2.3), -- the blade's -Y is the far end (away from the fist)
		hilt = att("Hilt", 2.3),
	}
	local m = job.motion or {}
	local raise, swingAt, swingTime = m.raise or 0.6, m.swingAt or 2.5, m.swingTime or 0.14
	-- phase: 0 = low guard, 1 = raised overhead (held), 2 = chopped down and forward
	local function phase(t: number): number
		if t < raise then
			local u = t / raise
			return 1 - (1 - u) * (1 - u)
		elseif t < swingAt then
			return 1
		end
		local u = math.clamp((t - swingAt) / swingTime, 0, 1)
		return 1 + u * u * (3 - 2 * u)
	end
	local function pose(t: number)
		local ph = phase(t)
		local a = math.min(ph, 1) -- 0..1 guard -> raised
		local b = math.max(0, ph - 1) -- 0..1 raised -> chopped
		-- shoulder pitch about X: + = the arm swings forward / up (0 hanging, 90 forward, 180 straight up)
		local shoulder = 30 * (1 - a) + 168 * a - 115 * b
		local elbow = 35 * (1 - a) + 18 * a - 10 * b -- + = the forearm folds forward
		local waist = 8 * a - 34 * b -- + = leans back
		local neck = 26 * a - 40 * b
		local roll = 14 * a -- the hands come together over the head
		local rot: { [string]: CFrame } = {
			RightShoulder = CFrame.Angles(math.rad(shoulder), 0, math.rad(roll)),
			LeftShoulder = CFrame.Angles(math.rad(shoulder), 0, math.rad(-roll)),
			RightElbow = CFrame.Angles(math.rad(elbow), 0, 0),
			LeftElbow = CFrame.Angles(math.rad(elbow), 0, 0),
			Waist = CFrame.Angles(math.rad(waist), 0, 0),
			Neck = CFrame.Angles(math.rad(neck), 0, 0),
			LeftHip = CFrame.Angles(math.rad(-38 * b), 0, 0), -- the left leg steps forward on the chop
			LeftKnee = CFrame.Angles(math.rad(28 * b), 0, 0),
			RightHip = CFrame.Angles(math.rad(16 * b), 0, 0),
		}
		-- the body drops and leans into the chop
		hrp.CFrame = CFrame.new(0, 3.0 - 0.35 * b, -0.6 * b)
		for _, name in order do
			local j = joints[name]
			if j then
				j.child.CFrame = j.parent.CFrame * j.a0.CFrame * (rot[name] or CFrame.identity) * j.a1.CFrame:Inverse()
			end
		end
		local h = hand.CFrame
		grip.CFrame = h * CFrame.new(0, 0.1, 0)
		guard.CFrame = h * CFrame.new(0, -0.4, 0)
		blade.CFrame = h * CFrame.new(0, -0.4 - 2.3, 0)
	end
	pose(0)
	return anchors, pose
end

local DEFAULT_VIEWS = {
	player = { pos = { 6, 8, 15 }, look = { -3, 5, -60 }, fov = 70 },
	side = { pos = { 110, 26, -120 }, look = { 0, 12, -125 }, fov = 62 },
	hero = { pos = { -15, 5, -24 }, look = { 0, 7, 0 }, fov = 66 },
	-- a cinematic path: close on the sword, a slow push-in while the light gathers, a snap behind the shoulder at the
	-- release, a sweep down the river of light, settling wide on the impact
	cine = {
		path = {
			{ t = 0.0, pos = { -10, 4.5, -14 }, look = { 0, 6, -1 }, fov = 58 },
			{ t = 2.3, pos = { -7, 6.5, -11 }, look = { 0, 7.5, -3 }, fov = 50 },
			{ t = 2.6, pos = { -58, 13, -4 }, look = { 0, 7, -70 }, fov = 64 },
			{ t = 3.0, pos = { -66, 15, -30 }, look = { 0, 8, -110 }, fov = 64 },
			{ t = 3.9, pos = { -90, 24, -130 }, look = { 0, 9, -215 }, fov = 66 },
			{ t = 5.2, pos = { -95, 30, -236 }, look = { 0, 14, -292 }, fov = 64 },
			{ t = 7.5, pos = { -100, 28, -240 }, look = { 0, 10, -292 }, fov = 64 },
		},
	},
}

local function v3(t: any): Vector3
	return Vector3.new(t[1], t[2], t[3])
end

-- ---------------------------------------------------------------- presentation (mission 02-vfx 5.8)
-- the effect judged like a game: the owner's R6 rig driven by a REAL attack clip, a post stack, a reacting ground.

-- booth.actor = { clip = "<Name>", hitAt = <effect seconds> [, weapon = false] }: an R6 character from Roblox's
-- own description plays the clip through its Animator, STEPPED on the effect clock (Animator:StepAnimations works
-- in Edit mode), placed so the clip's Hit marker lands on hitAt. A sword rides the right arm unless weapon = false
-- (then the tip / blade anchors are the right hand: a fist attack). The run copies the clip from the place
-- (ReplicatedStorage.KitAnimations.<clip>, the compiled src/animations/<clip>.model.json) to
-- ReplicatedStorage.KitVfxBooth.ActorClip, where a replay finds it too.
local function buildClipActor(root: Instance, job: any): ({ [string]: Instance }, (t: number) -> ())
	local Players = game:GetService("Players")
	local KSP = game:GetService("KeyframeSequenceProvider")
	local actor = job.actor
	local desc = Instance.new("HumanoidDescription")
	local cloth, armor, skin = Color3.fromRGB(38, 58, 140), Color3.fromRGB(196, 200, 210), Color3.fromRGB(240, 214, 190)
	desc.HeadColor, desc.TorsoColor = skin, armor
	desc.LeftArmColor, desc.RightArmColor, desc.LeftLegColor, desc.RightLegColor = cloth, cloth, cloth, cloth
	local model = Players:CreateHumanoidModelFromDescription(desc, Enum.HumanoidRigType.R6)
	model.Name = "Actor"
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") then
			d.Anchored = d.Name == "HumanoidRootPart"
			d.CanCollide = false
			d.CastShadow = true
		elseif d:IsA("LuaSourceContainer") then
			d:Destroy()
		end
	end
	local hum = model:FindFirstChildOfClass("Humanoid") :: Humanoid
	hum.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
	hum.HealthDisplayType = Enum.HumanoidHealthDisplayType.AlwaysOff
	local hrp = model:FindFirstChild("HumanoidRootPart") :: BasePart
	hrp.CFrame = CFrame.new(0, 3, 0) -- facing -Z, the effect's forward
	model.Parent = root
	local animator = hum:FindFirstChildOfClass("Animator") or Instance.new("Animator")
	animator.Parent = hum
	local stored = ReplicatedStorage:FindFirstChild("KitVfxBooth")
	local seq = ((stored :: Instance):FindFirstChild("ActorClip") :: KeyframeSequence):Clone()
	local hitT = 0
	for _, kf in seq:GetChildren() do
		if kf:IsA("Keyframe") then
			for _, mk in kf:GetChildren() do
				if mk:IsA("KeyframeMarker") and mk.Name == (actor.marker or "Hit") then
					hitT = kf.Time
				end
			end
		end
	end
	local animation = Instance.new("Animation")
	animation.AnimationId = KSP:RegisterKeyframeSequence(seq)
	local track = animator:LoadAnimation(animation)
	local t0 = os.clock()
	while track.Length <= 0 and os.clock() - t0 < 3 do -- a registered sequence loads asynchronously
		task.wait()
	end
	track.Looped = false
	track:Play(0, 1, 0) -- speed 0: the booth sets TimePosition itself
	local offset = (actor.hitAt or 0) - hitT -- effect time when the clip starts
	local arm = model:FindFirstChild("Right Arm") :: BasePart
	local sword = Instance.new("Model")
	sword.Name = "Sword"
	sword.Parent = root
	local weapon = actor.weapon ~= false
	local guard, grip, blade
	if weapon then
		guard = part({
			Name = "Guard",
			Size = Vector3.new(1.3, 0.22, 0.3),
			Color = Color3.fromRGB(220, 180, 70),
			Material = Enum.Material.Metal,
		}, sword)
		grip = part({ Name = "Grip", Size = Vector3.new(0.24, 0.9, 0.24), Color = Color3.fromRGB(40, 60, 150) }, sword)
		blade = part({
			Name = "Blade",
			Size = Vector3.new(0.34, 4.6, 0.09),
			Color = Color3.fromRGB(226, 230, 240),
			Material = Enum.Material.Metal,
			Reflectance = 0.2,
		}, sword)
	end
	local holder = blade or arm
	local function att(name: string, y: number): Attachment
		local a = Instance.new("Attachment")
		a.Name = name
		a.Position = Vector3.new(0, y, 0)
		a.Parent = holder
		return a
	end
	local anchors: { [string]: Instance } = {
		body = model,
		blade = holder,
		bladeMid = att("Mid", if weapon then 0 else -0.6),
		tip = att("Tip", if weapon then -2.3 else -1.1),
		hilt = att("Hilt", if weapon then 2.3 else -0.9),
	}
	local function pose(t: number)
		track.TimePosition = math.clamp(t - offset, 0, math.max(track.Length - 1e-3, 0))
		animator:StepAnimations(0)
		if weapon then
			-- the fist grips at the arm's end; the blade runs FORWARD out of it (the part's -Y = the far end)
			local h = arm.CFrame * CFrame.new(0, -1, 0) * CFrame.Angles(math.rad(90), 0, 0)
			grip.CFrame = h * CFrame.new(0, 0.1, 0)
			guard.CFrame = h * CFrame.new(0, -0.4, 0)
			blade.CFrame = h * CFrame.new(0, -0.4 - 2.3, 0)
		end
	end
	pose(0)
	return anchors, pose
end

-- booth.post = { grade = { contrast, saturation, brightness, tint }, dof = { far, focus, radius, near },
-- sunrays = { intensity, spread } }: the source's grade over the scene. The grade switches OFF whenever the effect's
-- own screen / impact grade is on (two ColorCorrections add: a flash frame must never be graded twice).
local function postStack(job: any): () -> ()
	for _, e in Lighting:GetChildren() do
		if e.Name == "KitBoothPost" then
			e:Destroy()
		end
	end
	local post = job.post
	if type(post) ~= "table" then
		return function() end
	end
	local grade: ColorCorrectionEffect? = nil
	if post.grade then
		local g = Instance.new("ColorCorrectionEffect")
		g.Name = "KitBoothPost"
		g.Contrast = post.grade.contrast or 0
		g.Saturation = post.grade.saturation or 0
		g.Brightness = post.grade.brightness or 0
		if post.grade.tint then
			g.TintColor = Color3.fromRGB(post.grade.tint[1], post.grade.tint[2], post.grade.tint[3])
		end
		g.Parent = Lighting
		grade = g
	end
	if post.dof then
		local d = Instance.new("DepthOfFieldEffect")
		d.Name = "KitBoothPost"
		d.FarIntensity = post.dof.far or 0.4
		d.FocusDistance = post.dof.focus or 20
		d.InFocusRadius = post.dof.radius or 18
		d.NearIntensity = post.dof.near or 0
		d.Parent = Lighting
	end
	if post.sunrays then
		local s = Instance.new("SunRaysEffect")
		s.Name = "KitBoothPost"
		s.Intensity = post.sunrays.intensity or 0.08
		s.Spread = post.sunrays.spread or 0.6
		s.Parent = Lighting
	end
	return function()
		if not grade then
			return
		end
		local effectGrade = false
		for _, e in Lighting:GetChildren() do
			if
				(e.Name == "KitVfxStage" or e.Name == "KitVfxImpact")
				and e:IsA("ColorCorrectionEffect")
				and e.Enabled
			then
				effectGrade = true
			end
		end
		grade.Enabled = not effectGrade
	end
end

-- booth.ground = { at = {x, y, z}, radius = studs, time = <effect seconds> }: the ground REACTS — a scorched crater
-- with a broken rim opens at the hit (dust and debris are the effect's own layers)
local function groundReaction(root: Instance, job: any): (t: number) -> ()
	local g = job.ground
	if type(g) ~= "table" then
		return function() end
	end
	local at = v3(g.at or { 0, 0, -12 })
	local r = g.radius or 6
	local crater = part({
		Name = "Crater",
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(0.2, 0.1, 0.1),
		CFrame = CFrame.new(at.X, 0.06, at.Z) * CFrame.Angles(0, 0, math.rad(90)),
		Color = Color3.fromRGB(28, 22, 20),
		Material = Enum.Material.Slate,
		Transparency = 1,
	}, root)
	local rocks = {}
	for k = 1, 14 do
		local a = k / 14 * math.pi * 2 + (k % 3) * 0.2
		table.insert(rocks, {
			a = a,
			part = part({
				Name = "Rim",
				Size = Vector3.new(1.2 + (k % 4) * 0.4, 0.8 + (k % 3) * 0.5, 1.4),
				Color = Color3.fromRGB(96, 80, 66),
				Material = Enum.Material.Rock,
				Transparency = 1,
			}, root),
		})
	end
	return function(t: number)
		local u = math.clamp((t - (g.time or 0)) / 0.12, 0, 1) -- the crater opens in 0.12 s
		crater.Transparency = if u > 0 then 0 else 1
		crater.Size = Vector3.new(0.2, 2 * r * u + 0.1, 2 * r * u + 0.1)
		for _, k in rocks do
			k.part.Transparency = if u > 0 then 0 else 1
			k.part.CFrame = CFrame.new(at.X + math.cos(k.a) * r * u, 0.3 * u, at.Z + math.sin(k.a) * r * u)
				* CFrame.Angles(math.rad(25), k.a, math.rad(-15))
		end
	end
end

-- the stage: lighting, arena, actor (fresh each time) -> anchors, pose(t), origin
local function stageScene(job: any): ({ [string]: Instance }, (t: number) -> (), CFrame)
	local old = Workspace:FindFirstChild("KitVfxBoothStage")
	if old then
		old:Destroy()
	end
	local root = Instance.new("Folder")
	root.Name = "KitVfxBoothStage"
	root.Parent = Workspace
	setLighting(job)
	local sceneAnchors: { [string]: Instance } = {}
	if type(job.scene) == "table" then
		sceneAnchors = buildScene(root, job.scene) -- G2: the scene file's arena + its victim
	else
		buildArena(root)
	end
	local post = postStack(job)
	local ground = groundReaction(root, job)
	local anchors, actorPose
	local booth = ReplicatedStorage:FindFirstChild("KitVfxBooth")
	if type(job.actor) == "table" and booth and booth:FindFirstChild("ActorClip") then
		anchors, actorPose = buildClipActor(root, job)
	else
		anchors, actorPose = buildActor(root, job)
	end
	for k, v in sceneAnchors do
		anchors[k] = v
	end
	local function pose(t: number)
		actorPose(t)
		ground(t)
		post()
	end
	return anchors, pose, CFrame.new(0, 0, 0)
end

-- a view: either a static frame or, for a path, a function of the effect time (the stage calls it every frame)
local function viewFrame(job: any, vname: string, origin: CFrame): ((t: number) -> (CFrame, number), CFrame, number)
	local v = (job.viewDefs and job.viewDefs[vname]) or DEFAULT_VIEWS[vname] or DEFAULT_VIEWS.player
	local function frame(pos: Vector3, look: Vector3): CFrame
		return CFrame.lookAt(origin:PointToWorldSpace(pos), origin:PointToWorldSpace(look))
	end
	if not v.path then
		local cf = frame(v3(v.pos), v3(v.look))
		return function()
			return cf, v.fov or 70
		end, cf, v.fov or 70
	end
	local keys = v.path
	local function at(t: number): (CFrame, number)
		if t <= keys[1].t then
			return frame(v3(keys[1].pos), v3(keys[1].look)), keys[1].fov or 70
		end
		for i = 1, #keys - 1 do
			local k0, k1 = keys[i], keys[i + 1]
			if t <= k1.t then
				local u = (t - k0.t) / math.max(k1.t - k0.t, 1e-3)
				u = u * u * (3 - 2 * u)
				local pos = v3(k0.pos):Lerp(v3(k1.pos), u)
				local look = v3(k0.look):Lerp(v3(k1.look), u)
				return frame(pos, look), (k0.fov or 70) + ((k1.fov or 70) - (k0.fov or 70)) * u
			end
		end
		local last = keys[#keys]
		return frame(v3(last.pos), v3(last.look)), last.fov or 70
	end
	local cf0, fov0 = at(0)
	return at, cf0, fov0
end

-- sounds in the booth: the kit's uploaded sounds (assets/ids.json), played at a point in edit mode
local function stopSounds()
	for _, c in Workspace:GetChildren() do
		if c.Name == "KitBoothSound" then
			c:Destroy()
		end
	end
end

local function soundShim(ids: any): any
	local sounds: { [string]: string } = if type(ids) == "table" and type(ids.sounds) == "table" then ids.sounds else {}
	return {
		play = function(name: string, where: Vector3, props: { [string]: any }?): Sound?
			local id = sounds[name]
			if not id then
				return nil
			end
			local holder = Instance.new("Part")
			holder.Anchored = true
			holder.Transparency = 1
			holder.CanCollide = false
			holder.CanQuery = false
			holder.Size = Vector3.one
			holder.Position = where
			holder.Name = "KitBoothSound"
			holder.Parent = Workspace
			local snd = Instance.new("Sound")
			snd.SoundId = id
			local extra: { [string]: any } = props or {}
			for k, v in extra do
				(snd :: any)[k] = v
			end
			snd.Parent = holder
			snd:Play()
			snd.Ended:Once(function()
				holder:Destroy()
			end)
			task.delay(30, function()
				if holder.Parent then
					holder:Destroy()
				end
			end)
			return snd
		end,
	}
end

local function cache(folder: Instance, name: string, text: string)
	local sv = Instance.new("StringValue")
	sv.Name = name
	sv.Value = text
	sv.Parent = folder
end

-- watch the last booth effect LIVE at real speed, no capture (Studio in front = full frame rate):
--   require(game.ServerStorage.KitStudioBridge.VfxBooth).replay("hero")      views: player | side | hero
local function replay(vname: string?): string
	local folder = ReplicatedStorage:FindFirstChild("KitVfxBooth")
	local kit = folder and folder:FindFirstChild("kit")
	if not (folder and kit and folder:FindFirstChild("PresetJson") and kit:FindFirstChild("VfxStage")) then
		return "no booth run in this place yet: run `lune run kit vfx booth <name>` once (it keeps the effect here)"
	end
	local VfxStage = (require :: any)((kit :: Instance):FindFirstChild("VfxStage"))
	local preset = Bridge.decode((folder:FindFirstChild("PresetJson") :: StringValue).Value)
	local textures = Bridge.decode((folder:FindFirstChild("TexturesJson") :: StringValue).Value)
	local job = Bridge.decode((folder:FindFirstChild("JobJson") :: StringValue).Value)
	stopSounds()
	local anchors, pose, origin = stageScene(job)
	local camera = Workspace.CurrentCamera
	camera.CameraType = Enum.CameraType.Scriptable
	local camAt, camCF, fov = viewFrame(job, vname or "hero", origin)
	camera.CFrame = camCF
	camera.FieldOfView = fov
	local idsNode = folder:FindFirstChild("IdsJson")
	VfxStage.preload(preset, textures)
	local stage = VfxStage.play(preset, origin, {
		booth = true,
		cameraBase = camAt,
		cameraFov = fov,
		textures = textures,
		anchors = anchors,
		name = job.name,
		assets = soundShim(if idsNode then Bridge.decode((idsNode :: StringValue).Value) else nil),
		mute = ((job.viewDefs and job.viewDefs[vname or "hero"]) or {}).mute or job.mute,
	})
	local conn: RBXScriptConnection
	conn = RunService.Heartbeat:Connect(function()
		pose(stage.time)
		if stage.finished then
			conn:Disconnect()
			pose(0)
		end
	end)
	return `playing {job.name} from the {vname or "hero"} view ({stage.duration} s)`
end

local function answer(t: { [string]: any }): string
	t.schema = 1
	return Bridge.encode(t)
end

-- one booth run: the job (a JSON text, from the run's .studio.luau) -> the answer line. A run lasts minutes, longer
-- than one Studio tool call: it answers at once with status "started" (how long, and the collect script) and keeps
-- its final answer for <run>.collect.luau (Bridge.store)
local function run(jobText: string): string
	local job = Bridge.decode(jobText)
	local key = job.key or "vfx_booth"
	local placeKit = ReplicatedStorage:FindFirstChild("kit")
	if not (placeKit and placeKit:FindFirstChild("VfxStage") and placeKit:FindFirstChild("VfxCompose")) then
		return answer({
			status = "fail",
			summary = "this place holds no ReplicatedStorage.kit (VfxStage, VfxCompose): it is not the kit's scratch place",
			next_action = "build and open it: lune run kit playtest place (KitPlaytestScratch)",
		})
	end
	if type(job.presetDoc) ~= "table" then
		return answer({
			status = "fail",
			summary = "the job carries no preset",
			next_action = "lune run kit vfx booth <name>",
		})
	end
	local clipSource: Instance? = nil
	if type(job.actor) == "table" and type(job.actor.clip) == "string" then -- the presentation rig's clip
		local anims = ReplicatedStorage:FindFirstChild("KitAnimations")
		clipSource = anims and anims:FindFirstChild(job.actor.clip)
		if not (clipSource and clipSource:IsA("KeyframeSequence")) then
			return answer({
				status = "fail",
				summary = `this place has no ReplicatedStorage.KitAnimations.{job.actor.clip} (the stage's clip)`,
				next_action = "rebuild the scratch place (lune run kit playtest place) after the clip is compiled, and reopen it",
			})
		end
	end
	local staleKit = Bridge.staleKit(placeKit, job.kitPrints)
	-- fresh kit modules: a COPY of the place's src/kit each run (require caches a script's first result per session)
	local folder = ReplicatedStorage:FindFirstChild("KitVfxBooth")
	if folder then
		folder:Destroy()
	end
	folder = Instance.new("Folder")
	folder.Name = "KitVfxBooth"
	folder.Parent = ReplicatedStorage
	local kit = (placeKit :: Instance):Clone()
	kit.Parent = folder
	local VfxStage = (require :: any)(kit:FindFirstChild("VfxStage"))
	local preset = job.presetDoc
	if type(job.evolve) == "table" then -- an evolve variant (kit vfx evolve): over the preset's own overlay, this run
		local baseOverlay = if type(preset.overlay) == "table" then preset.overlay else {}
		local e = job.evolve
		local mute = {}
		for _, list in { baseOverlay.mute or {}, e.mute or {} } do
			for _, m in list do
				table.insert(mute, m)
			end
		end
		preset.overlay = {
			time = (baseOverlay.time or 1) * (e.time or 1),
			scale = (baseOverlay.scale or 1) * (e.scale or 1),
			saturate = (baseOverlay.saturate or 0) + (e.saturate or 0),
			mute = mute,
		}
	end
	do -- beats / use / variants / overlay expand here too (the file on disk is the composed form)
		local VfxCompose = (require :: any)(kit:FindFirstChild("VfxCompose"))
		local parts = if type(job.parts) == "table" then job.parts else {}
		local issues
		preset, issues = VfxCompose.expand(preset, {
			variant = job.variant,
			parts = function(partName: string): any?
				return parts[partName]
			end,
		})
		if #issues > 0 then
			folder:Destroy()
			return answer({
				status = "fail",
				summary = `preset {job.name}: {issues[1].path}: {issues[1].message}`,
				next_action = `lune run kit vfx {job.name}`,
			})
		end
		if job.surface then -- the --surface experiment: textured mesh layers drawn as SurfaceAppearances this run
			for _, el in preset.layers do
				if el.kind == "mesh" and el.texture and el.surface == nil then
					el.surface = job.surface
				end
			end
		end
	end
	local textures = if type(job.textures) == "table" then job.textures else {}
	local boothCfg = preset.booth or {}
	for k, v in boothCfg do
		if k == "viewDefs" and type(v) == "table" then
			job.viewDefs = job.viewDefs or {}
			for viewName, def in v do
				job.viewDefs[viewName] = def -- the preset's own cameras win over the shared kit/vfx/views.json
			end
		elseif job[k] == nil then
			job[k] = v
		end
	end
	if clipSource then
		local clip = clipSource:Clone()
		clip.Name = "ActorClip"
		clip.Parent = folder
	end
	local okIds, ids = pcall(function()
		return (require :: any)(ReplicatedStorage:FindFirstChild("AssetIds"))
	end)
	if not (okIds and type(ids) == "table") then
		ids = nil
	end
	-- kept in the place so the effect can be replayed live later (see replay above)
	cache(folder, "PresetJson", Bridge.encode(preset))
	cache(folder, "TexturesJson", Bridge.encode(textures))
	cache(folder, "JobJson", Bridge.encode(job))
	if ids then
		cache(folder, "IdsJson", Bridge.encode(ids))
	end

	stopSounds()
	local anchors, pose, origin = stageScene(job)
	local camera = Workspace.CurrentCamera
	camera.CameraType = Enum.CameraType.Scriptable

	local views = job.views or { "player", "side", "hero", "cine" }
	local moments = job.moments
		or { 0.1, 0.4, 0.8, 1.2, 1.6, 2.0, 2.3, 2.45, 2.55, 2.62, 2.7, 2.85, 3.05, 3.4, 3.9, 4.6, 5.5, 6.5 }
	-- moments: numbers only, sorted, no repeats (the clock never runs backwards)
	local clean, seen = {}, {}
	for _, t in moments do
		if type(t) == "number" and t >= 0 and not seen[t] then
			seen[t] = true
			table.insert(clean, t)
		end
	end
	table.sort(clean)
	moments = clean
	local scaleT = job.timeScale or 0.5
	-- Particles only simulate on rendered frames, and an unfocused Studio renders ~5 times a second. Each step
	-- between two moments must last >= ~0.4 s of real time or the particles fall behind the clock (dense video
	-- moments: slow the stage down so every step spans a couple of rendered frames).
	local minStep = math.huge
	for i = 2, #moments do
		minStep = math.min(minStep, moments[i] - moments[i - 1])
	end
	if minStep < math.huge then
		scaleT = math.min(scaleT, minStep / 0.4)
	end
	local settle = job.settle or 0.4
	local capture = if type(job.capture) == "table" then job.capture else {}
	local flash, hold = capture.flash or 0.6, capture.hold or 1.0
	local last = if #moments > 0 then moments[#moments] else 0
	local seconds =
		math.ceil(#views * (last / math.max(scaleT, 0.01) + #moments * (settle + flash + hold) + 2) + 3 * flash)
	local stale = Bridge.staleWords(staleKit, {})
	local base = {
		key = key,
		preset = job.name,
		views = views,
		moments = moments,
		timeScale = scaleT,
		stale = staleKit,
		stale_words = stale,
	}
	folder:SetAttribute("Status", "running")
	Bridge.store(key, answer({ status = "running", summary = `booth {job.name} still running (about {seconds} s)` }))
	task.spawn(function()
		local current: any = nil -- the stage on screen: stopped on an error too, so the place is never left dirty
		local poseConn: RBXScriptConnection? = nil
		local grabs = {}
		local sig = Bridge.signal({ flash = flash })
		local ok, err = pcall(function()
			VfxStage.preload(preset, textures)
			sig.start()
			local k = 1
			sig.next(k) -- (the next picture's colour is up whenever the view is not held for a picture)
			for _, vname in views do
				local camAt, camCF, fov = viewFrame(job, vname, origin)
				camera.CFrame = camCF
				camera.FieldOfView = fov
				local stage = VfxStage.play(preset, origin, {
					booth = true,
					cameraBase = camAt,
					cameraFov = fov,
					textures = textures,
					anchors = anchors,
					name = job.name,
					noShake = job.noShake,
					assets = soundShim(ids),
					mute = ((job.viewDefs and job.viewDefs[vname]) or {}).mute or job.mute, -- a view may mute its own layers
				})
				current = stage
				local conn = RunService.Heartbeat:Connect(function()
					pose(stage.time)
				end)
				poseConn = conn
				stage:setTimeScale(scaleT)
				for i, t in moments do
					if t >= stage.duration then
						break
					end
					stage:advanceTo(t)
					local waited = 0
					while not stage.frozen and not stage.finished and waited < 30 do
						waited += task.wait()
					end
					pose(stage.time)
					task.wait(settle)
					sig.hide() -- the frozen frame, held still for the capture
					table.insert(grabs, { k = k, view = vname, i = i, t = math.round(stage.time * 1000) / 1000 })
					task.wait(hold)
					k += 1
					sig.next(k)
				end
				conn:Disconnect()
				stage:stop()
				stopSounds()
				pose(0)
			end
		end)
		if poseConn then
			poseConn:Disconnect()
		end
		if current and not current.finished then
			current:stop()
		end
		pose(0)
		sig.finish()
		folder:SetAttribute("Status", if ok then "done" else "error: " .. tostring(err))
		local final = table.clone(base)
		final.status = if ok and #grabs > 0 then "pass" else "fail"
		final.grabs = grabs
		final.summary = if ok
			then `booth {job.name}: {#grabs} picture(s) signalled in {#views} view(s)` .. (if stale
				then "; " .. stale
				else "")
			else `booth {job.name} stopped: {tostring(err)}`
		if not ok then
			final.error = tostring(err)
		end
		Bridge.store(key, answer(final))
	end)
	local started = table.clone(base)
	started.status = "started"
	started.seconds = seconds
	started.collect = job.collect
	started.summary = `booth {job.name}: {#views} view(s) x {#moments} moment(s), time scale {scaleT}, about {seconds} s`
		.. (if stale then "; " .. stale else "")
	started.next_action =
		`wait about {seconds} s, then run {job.collect or "the run's .collect.luau"} and save its line as the capture asks`
	return answer(started)
end

return setmetatable({ run = run, replay = replay }, {
	-- (the old call form: (nil, view) replays the last run)
	__call = function(_, _port: any, view: string?): string
		return replay(view)
	end,
})

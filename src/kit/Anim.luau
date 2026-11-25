-- Anim (ReplicatedStorage.kit.Anim) — play kit animations (assets/animations/* → ReplicatedStorage.KitAnimations)
-- by NAME on any Humanoid / AnimationController, and run the kit's LOCOMOTION blend.
--   local track = Anim.play(humanoid, "Slash")                  -- returns the AnimationTrack (or nil)
--   Anim.marker(track, "Swing"):Connect(playWhoosh)   -- a clip's events, each taken once a pass (AnimMarks);
--   damage is NOT hung on a marker: the server's Moves decides hits from the move's frame data
--   Anim.load(humanoid, "Slash")                                 -- load without playing (preload on spawn)
--   local loco = Anim.locomotion(character, { idle = "Idle", walk = "Walk", run = "Run" })
--   loco:stop()                                                  -- give the character back to Roblox's Animate
--                                                                   (automatic when it dies or is removed)
-- Id resolution: an uploaded id (kit asset-id ... animations/<name>) wins; otherwise, IN STUDIO ONLY, the
-- KeyframeSequence is registered on the fly (KeyframeSequenceProvider) so you can playtest before uploading.
-- Live games need the upload: `lune run kit upload` (both rig versions; ids land in assets/ids.json).
-- Every clip compiles to two KeyframeSequences: <Name> (R6) and <Name>_R15 (R15, including the newer
-- AnimationConstraint avatars). Anim picks the one that matches the Humanoid's RigType.
-- Locomotion: the clips' measured ground speeds (ReplicatedStorage.KitAnimations.Meta, written by kit anim) set each
-- track's playback rate so the planted foot moves back at the character's real speed; weights come from AnimBlend.
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local AnimBlend = require(script.Parent.AnimBlend)
local AnimFeel = require(script.Parent.AnimFeel)
local AnimLayers = require(script.Parent.AnimLayers)
local AnimMarks = require(script.Parent.AnimMarks)
local AnimMatch = require(script.Parent.AnimMatch)
local AnimRules = require(script.Parent.AnimRules)
local AnimWarp = require("./AnimWarp")

local Anim = {}

local cache: { [string]: string } = {}

-- quiet: a lookup that may miss on purpose (an R6-native clip has no "_R15" variant) - no warning
local function animationId(name: string, quiet: boolean?): string?
	if cache[name] then
		return cache[name]
	end
	local registry = ReplicatedStorage:FindFirstChild("AssetIds")
	if registry then
		local okIds, ids = pcall(require, registry :: ModuleScript)
		local id = okIds and type(ids) == "table" and ids.animations and ids.animations[name]
		if type(id) == "string" and id ~= "" then
			cache[name] = id
			return id
		end
	end
	local folder = ReplicatedStorage:FindFirstChild("KitAnimations")
	local seq = folder and folder:FindFirstChild(name)
	if not seq then
		if not quiet then
			warn(`[Anim] no animation "{name}" (assets/animations/{name}.json → lune run kit anim)`)
		end
		return nil
	end
	if RunService:IsStudio() then
		local ok, id = pcall(function()
			-- (a CurveAnimation - src/kit/AnimCurve - is registered the same way; the engine plays it at 30 samples a
			-- second, so the kit's own 60-a-second clips stay KeyframeSequences)
			if seq:IsA("CurveAnimation") then
				return game:GetService("AnimationClipProvider"):RegisterAnimationClip(seq)
			end
			return game:GetService("KeyframeSequenceProvider"):RegisterKeyframeSequence(seq :: KeyframeSequence)
		end)
		if ok then
			cache[name] = id
			return id
		end
		warn(`[Anim] could not register "{name}" in Studio: {id}`)
		return nil
	end
	warn(`[Anim] "{name}" has no uploaded id — publish it, then: lune run kit asset-id animations/{name} <id>`)
	return nil
end

-- THE WAY A BODY IS GOING (world, length 0..1): what its Humanoid is asked, or - walked by Humanoid:MoveTo, which
-- leaves MoveDirection at zero - the way it moves on foot (the rule and why: AnimBlend.going)
-- the velocity of the floor under a body (a conveyor, a train, a turning disc; zero on still ground or in the air).
-- Asked only when the body moves at all: one ray down from its root
local function floorVelocity(character: Instance?, humanoid: Humanoid, root: BasePart, velocity: Vector3): Vector3
	if not character or velocity.Magnitude < AnimBlend.IDLE_SPEED then
		return Vector3.zero
	end
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { character }
	local reach = humanoid.HipHeight + root.Size.Y / 2 + 3
	local floor = workspace:Raycast(root.Position, Vector3.new(0, -reach, 0), params)
	return if floor then floor.Instance:GetVelocityAtPosition(floor.Position) else Vector3.zero
end

function Anim.going(humanoid: Humanoid): Vector3
	local move = humanoid.MoveDirection
	local root = humanoid.RootPart
	local v = if root then root.AssemblyLinearVelocity else Vector3.zero
	local onFoot = AnimBlend.onFoot(humanoid:GetState().Name, humanoid.PlatformStand, humanoid.Sit)
	local character = humanoid.Parent
	if root and character and onFoot and move.Magnitude <= 1e-3 and v.Magnitude >= AnimBlend.IDLE_SPEED then
		-- (asked nothing and moving: the floor's own velocity comes off first - a body standing still on a conveyor,
		-- a train or a turning disc is carried, not walking. An anchored conveyor says its belt speed here too)
		v -= floorVelocity(character, humanoid, root, v)
	end
	local x, z = AnimBlend.going(move.X, move.Z, v.X, v.Z, humanoid.WalkSpeed, onFoot)
	return Vector3.new(x, 0, z)
end

local function animatorOf(owner: Instance): Animator?
	local animator = owner:FindFirstChildOfClass("Animator")
	if animator then
		return animator
	end
	if owner:IsA("Humanoid") or owner:IsA("AnimationController") then
		local created = Instance.new("Animator")
		created.Parent = owner
		return created
	end
	return nil
end

-- the version of `name` that fits this owner's rig (R15 -> "<name>_R15" when it exists)
local function forRig(owner: Instance, name: string): string
	local humanoid = if owner:IsA("Humanoid") then owner else owner:FindFirstChildOfClass("Humanoid")
	if humanoid and (humanoid :: Humanoid).RigType == Enum.HumanoidRigType.R15 then
		local r15 = name .. "_R15"
		local folder = ReplicatedStorage:FindFirstChild("KitAnimations")
		local registry = ReplicatedStorage:FindFirstChild("AssetIds")
		local okIds, ids = pcall(function()
			return if registry then require(registry :: ModuleScript) :: any else nil
		end)
		local uploaded = okIds and type(ids) == "table" and ids.animations and ids.animations[r15]
		if uploaded or (folder and folder:FindFirstChild(r15)) then
			return r15
		end
		warn(`[Anim] "{name}" has no R15 version — run: lune run kit anim (R6 poses do nothing on an R15 rig)`)
	end
	return name
end

function Anim.load(owner: Instance, name: string): AnimationTrack?
	name = forRig(owner, name)
	local id = animationId(name)
	local animator = animatorOf(owner)
	if not id or not animator then
		return nil
	end
	local animation = Instance.new("Animation")
	animation.Name = name
	animation.AnimationId = id
	return animator:LoadAnimation(animation)
end

-- ROOT MOTION: a one-shot whose metadata carries a `root` track (a dash, a lunge, a roll) MOVES the character along
-- it (AnimFeel.rootAt) from where it started, read off the track's TimePosition - a hit-stop (AdjustSpeed(0)) holds
-- the travel too. Only on the machine that owns the body: the local player's character on its client, an NPC on the
-- server (a player's character on the server is moved by its client).
local function owns(character: Instance): boolean
	local Players = game:GetService("Players")
	local player = Players:GetPlayerFromCharacter(character)
	if RunService:IsServer() then
		return player == nil
	end
	return player ~= nil and player == Players.LocalPlayer
end

local rooted: { [AnimationTrack]: boolean } = setmetatable({}, { __mode = "k" }) :: any
-- one draw / one camera per track, whichever of Anim.play and the client watchers sees it first
local drawn: { [AnimationTrack]: boolean } = setmetatable({}, { __mode = "k" }) :: any
local cammed: { [AnimationTrack]: boolean } = setmetatable({}, { __mode = "k" }) :: any
local cameraTrack: (owner: Instance, track: AnimationTrack, keys: { any }) -> () -- (defined below Anim.additive)

-- ONE EFFECT FOR ONE MARKER (src/kit/AnimMarks holds the rule and what the engine was measured to do): a track's
-- markers are taken through one record a track - a marker crossed twice in one pass (the clip's time wound back)
-- runs its handler once; a loop or a new play is a new pass; nothing runs after the track stopped. The handler
-- gets the marker's value and its presentation record (the marker's OWN time in the clip, how late the handler is).
--   Anim.marker(track, "Hit", events):Connect(function(value, record) ... end)      events: the clip's (Meta), optional
--   Anim.newPass(track)     a track played again WHILE it plays (its time back at 0) is a new action: say so
local kicks: { [Humanoid]: { delta: Vector3, turn: number } } = setmetatable({}, { __mode = "k" }) :: any
local kicked: { [AnimationTrack]: boolean } = setmetatable({}, { __mode = "k" }) :: any
type MarkInfo = { state: AnimMarks.State, stopped: boolean }
local marks: { [AnimationTrack]: MarkInfo } = setmetatable({}, { __mode = "k" }) :: any
local function marksOf(track: AnimationTrack): MarkInfo
	local info = marks[track]
	if not info then
		local made: MarkInfo = { state = AnimMarks.new(), stopped = false }
		info = made
		marks[track] = made
		track.DidLoop:Connect(function()
			AnimMarks.pass(made.state)
		end)
		track.Stopped:Connect(function()
			AnimMarks.cancel(made.state)
			made.stopped = true
		end)
	end
	return info
end

export type Marker = {
	Connect: (self: Marker, fn: (value: string?, record: AnimMarks.Record) -> ()) -> RBXScriptConnection,
}

function Anim.marker(track: AnimationTrack, name: string, events: { any }?): Marker
	local info = marksOf(track)
	local marker = {}
	function marker.Connect(_self: Marker, fn: (value: string?, record: AnimMarks.Record) -> ()): RBXScriptConnection
		-- (each connection takes the marker for itself: two handlers on one marker - the kit's camera kick and a
		-- game's sound on "Hit" - both run. Sharing one record, only whichever came first did)
		local mine = AnimMarks.listener()
		return track:GetMarkerReachedSignal(name):Connect(function(value: string?)
			if not track.IsPlaying then
				return
			end
			if info.stopped then -- (it stopped and plays again: a new pass)
				info.stopped = false
				AnimMarks.pass(info.state)
			end
			local record =
				AnimMarks.take(info.state, name, track.TimePosition, events, mine, track.Looped, track.Length)
			if record then
				fn(value, record)
			end
		end)
	end
	return marker :: any
end

-- a track played again WHILE it plays is a new action (the engine gives no sign of it): say so
function Anim.newPass(track: AnimationTrack)
	AnimMarks.pass(marksOf(track).state)
end

-- a move CANCELLED while its track still plays out: none of its markers run any more (until the track plays again)
function Anim.cancelMarkers(track: AnimationTrack)
	local info = marksOf(track)
	AnimMarks.cancel(info.state)
	info.stopped = true
end

-- the markers a clip ENTERED at `at` seconds jumped over (the engine never fires them): for a game to apply the
-- ones that set a state and drop the one-shots; the kit applies its own (a face, a vanish) by itself
function Anim.skippedMarkers(clip: string, at: number): { AnimMarks.Event }
	local m = (Anim.meta() :: any)[clip]
	return AnimMarks.skipped(if m then m.events else nil, 0, at)
end

-- THE LAYERS ON ONE JOINT (the runtime layers write Motor6D.Transform after the Animator: look-at, additive, feet).
-- ONE record a joint, shared by every layer (AnimLayers.stackBase / stackWrite / stackRelease hold the rule):
--   the first layer to touch the joint in a frame builds on the Animator's value - or, when no track rewrote the
--   joint since the layers' last write, on the clean value under it (an offset on a joint nothing animates would
--   otherwise compound every frame and the limb spins away: review 2026-10-22);
--   every later layer in the same frame builds on what the layer before it wrote (they STACK);
--   when the last layer leaves, a joint that still holds the layers' write gets its clean value back.
-- Until 2026-11-15 each layer kept its OWN record: two layers on a joint no track drives each took the other's write
-- for the Animator's and built on it again - seen in Studio: two look-at layers on a still neck read 121, 75, 39
-- degrees a quarter second apart, and left it turned 12.9 degrees after both had stopped (the owner's list, AN-29).
-- The blend when a clip starts (inertialize, below) and the get-up out of a ragdoll (src/kit/AnimRagdoll) write the
-- same joints: they share the record too (AnimLayers.stackOf) - each keeping its own, a look-at on a still neck
-- under either of them added its turn again every frame (the one review, 2026-11-15).
type LayerMem = { [Motor6D]: boolean } -- the joints one layer has written
-- (the engine keeps Transform in single precision: the value read back is never EXACTLY the one written - the
-- playtest's untouched shoulder compounded 30 -> 60 -> 90 deg on an exact == check)
local function sameCF(a: CFrame, b: CFrame): boolean
	return (a.Position - b.Position).Magnitude < 1e-3
		and (a.XVector - b.XVector).Magnitude < 1e-4
		and (a.YVector - b.YVector).Magnitude < 1e-4
end
-- frame: the same number for every layer in one frame (RunService.Stepped's first argument)
local function layerBase(motor: Motor6D, mem: LayerMem, frame: number): CFrame
	local stack = AnimLayers.stackOf(motor)
	if not mem[motor] then
		mem[motor] = true
		stack.users += 1
	end
	return AnimLayers.stackBase(stack, motor.Transform, frame, sameCF, mem)
end
local function layerWrite(motor: Motor6D, _mem: LayerMem, value: CFrame)
	motor.Transform = value
	AnimLayers.stackWrite(AnimLayers.stackOf(motor), value)
end
-- the pose the clip plays on a joint, read outside a layer's own frame: what is UNDER the layers' last write
local function layerClean(motor: Motor6D): CFrame
	return AnimLayers.stackClean(AnimLayers.stackOf(motor), motor.Transform, sameCF)
end
-- a layer ENDS: a joint no track drives still holds the layers' last write - when this was the last layer on it, it
-- gets its clean value back (the playtest's untouched shoulder stayed bent after the layer ended)
local function layerRelease(mem: LayerMem)
	for motor in mem do
		local back = AnimLayers.stackRelease(AnimLayers.stackOf(motor), motor.Transform, sameCF)
		if back then
			motor.Transform = back -- (a joint out of the tree too: put back under a body, it must not keep the offset)
		end
	end
	table.clear(mem)
end

-- MOTION WARPING (AAA gaps v2 C5): the target the move reaches for - passed in, or an ObjectValue "KitWarpTarget" the
-- server's Moves leaves on the character (the client that owns the body moves it)
local function warpTargetOf(character: Instance, given: BasePart?): BasePart?
	if given then
		return given
	end
	local v = character:FindFirstChild("KitWarpTarget")
	if v and v:IsA("ObjectValue") and v.Value and v.Value:IsA("BasePart") then
		return v.Value :: BasePart
	end
	return nil
end

-- enteredAt: the clip's time it was ENTERED at (pose / distance matching): the body travels only what is left of
-- the root track from there, not the whole of it
-- (what a later caller knows about a travel already claimed: Anim.play's target and entry time reach the loop the
-- client's watcher started for the same track - whichever of the two sees the track first)
local rootAsks: { [AnimationTrack]: { target: BasePart?, enteredAt: number? } } = setmetatable({}, { __mode = "k" }) :: any

local function applyRoot(owner: Instance, track: AnimationTrack, clipMeta: any, target: BasePart?, enteredAt: number?)
	local known = rootAsks[track]
	if rooted[track] then
		-- (played on this machine AND seen by the watcher: one travel, not two)
		if known then
			known.target = known.target or target
			known.enteredAt = known.enteredAt or enteredAt
		end
		return
	end
	local raw = clipMeta and clipMeta.root
	if type(raw) ~= "table" or #raw < 2 then
		return
	end
	-- (Meta carries one "x z yaw" string per frame; a spin's yaw is unwrapped so it turns the short way round)
	local root = AnimWarp.rows(raw)
	if #root < 2 then
		return
	end
	local character = if owner:IsA("Humanoid") or owner:IsA("AnimationController") then owner.Parent else owner
	if not character or not character:IsA("Model") or not owns(character) then
		return
	end
	local part = character:FindFirstChild("HumanoidRootPart")
	if not part or not part:IsA("BasePart") then
		return
	end
	local rootPart = part :: BasePart
	rooted[track] = true
	local ask = { target = target, enteredAt = enteredAt }
	rootAsks[track] = ask
	local fps = tonumber(clipMeta.fps) or 30
	local window = AnimWarp.window(clipMeta.warp)
	-- THE TRAVEL AND THE WORLD (src/kit/AnimWarp, the owner's limitations list A-R04): the travel is swept for what
	-- stands in its way before the move and frame by frame, the target is followed until the move commits, and a body
	-- something else moved on purpose keeps its new place. Written, never seen to move (Studio).
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { character }
	params.RespectCanCollide = true
	local over = OverlapParams.new()
	over.FilterType = Enum.RaycastFilterType.Exclude
	over.FilterDescendantsInstances = { character }
	over.RespectCanCollide = true
	-- the body as it is swept: a BOX the torso's own width and depth, turned the way the body faces, from above the
	-- legs to the head's top (a step or a ramp under 2.5 studs is the Humanoid's to climb, a wall is not) - the ball
	-- it was (0.9 studs) was narrower than the shoulders and let a post 1 stud off the line through them
	-- (LIMITATIONS_FIXES_V4 4.4 / 13.4.3: workspace:Blockcast; AnimWarp.sweepBox holds the shape). A cast does not
	-- see what it STARTS inside, so a body already against a wall is caught by a smaller box at the place it would go
	local function yawOf(cf: CFrame): number
		local look = cf.LookVector
		return math.atan2(-look.X, -look.Z)
	end
	local torso = character:FindFirstChild("Torso") or character:FindFirstChild("UpperTorso")
	local shape = AnimWarp.sweepBox(
		if torso and torso:IsA("BasePart") then torso.Size.X else 2,
		if torso and torso:IsA("BasePart") then torso.Size.Z else 1
	)
	local SIZE = Vector3.new(shape.size[1], shape.size[2], shape.size[3])
	local BOX_PROBE = Vector3.new(shape.probe[1], shape.probe[2], shape.probe[3])
	local BALL, PROBE, RAISE = 0.9, 0.45, 0.4 -- (the ball it was: kept for an engine without Blockcast)
	local boxes = true
	local function cast(ax: number, az: number, bx: number, bz: number, extra: number): number?
		local dir = Vector3.new(bx - ax, 0, bz - az)
		local len = dir.Magnitude
		if len < 1e-4 then
			return nil
		end
		if boxes then
			local yb = rootPart.Position.Y + shape.up
			local facing = CFrame.Angles(0, yawOf(rootPart.CFrame), 0)
			local ok, hit = pcall(function()
				return workspace:Blockcast(CFrame.new(ax, yb, az) * facing, SIZE, dir.Unit * (len + extra), params)
			end)
			if ok then
				if hit then
					return hit.Distance
				end
				if #workspace:GetPartBoundsInBox(CFrame.new(bx, yb, bz) * facing, BOX_PROBE, over) > 0 then
					return 0
				end
				return nil
			end
			boxes = false
		end
		local y = rootPart.Position.Y + RAISE
		local from = Vector3.new(ax, y, az)
		local hit = workspace:Spherecast(from, BALL, dir.Unit * (len + extra), params)
		if hit then
			return hit.Distance
		end
		if #workspace:GetPartBoundsInRadius(Vector3.new(bx, y, bz), PROBE, over) > 0 then
			return 0
		end
		return nil
	end
	local function targetNow(): { number }?
		local tgt = warpTargetOf(character, ask.target)
		if not tgt or not tgt.Parent then
			return nil
		end
		return { tgt.Position.X, tgt.Position.Z }
	end
	local state: AnimWarp.State? = nil
	-- TIMING THAT FOLLOWS THE DISTANCE (AnimWarp.pace, the owner's older list AN-14): a clip whose warp says
	-- `pace` is played slower where it stands and faster where it travels - or the other way - for the distance the
	-- warp reaches; the time to the window's end does not change (AnimWarp.paceStep is the whole rule)
	local paceClock: AnimWarp.PaceClock? = nil
	-- (a clip plays on the GAME's time - time(), what Stepped counts - not the wall clock: measured in Studio, a
	-- throttled session ran 2.01 s of clip and of time() in 2.91 s of os.clock. The pace is planned in clip time)
	local lastGame = time()
	local last = os.clock()
	local conn: RBXScriptConnection? = nil
	conn = RunService.Heartbeat:Connect(function()
		if AnimWarp.cancelled(track.IsPlaying, rootPart.Parent ~= nil) then
			if conn then
				conn:Disconnect()
			end
			return
		end
		local now = os.clock()
		local dt = now - last
		last = now
		local t = track.TimePosition
		local here = rootPart.Position
		local s: AnimWarp.State? = state
		if not s then
			-- the travel begins where the clip IS on this machine's first frame of it (entered late by pose or
			-- distance; started on the server and seen here some way in): only what is left is travelled
			local t0 = if ask.enteredAt and ask.enteredAt > 0 then math.min(ask.enteredAt, t) else t
			s = AnimWarp.begin(
				root,
				fps,
				t0,
				{ x = here.X, z = here.Z, yaw = yawOf(rootPart.CFrame) },
				window,
				targetNow(),
				cast
			)
			state = s
			if window and window.pace then
				paceClock = AnimWarp.paceClock()
			end
		end
		local clock = paceClock
		if clock and window then
			local warp = (s :: AnimWarp.State).warp
			-- (the plan begins on the frame it is first made: the time before it is not its own)
			local gameNow = time()
			local paceDt = if clock.scale == nil then 0 else gameNow - lastGame
			lastGame = gameNow
			local want =
				AnimWarp.paceStep(clock, root, fps, window, if warp then warp.scale else nil, t, paceDt, track.Speed)
			if want then
				track:AdjustSpeed(want)
			end
			if clock.done then
				paceClock = nil
			end
		end
		local x, z, yaw =
			AnimWarp.step(s :: AnimWarp.State, root, fps, t, dt, here.X, here.Z, window, targetNow(), cast)
		rootPart.CFrame = CFrame.new(x, here.Y, z) * CFrame.Angles(0, yaw, 0)
	end)
end

-- the clip a playing track belongs to: its Animation's name (Anim.load names it), else its id (the uploaded ids, for a
-- track the SERVER started - Moves plays player moves there - whose Animation instance the client may not see)
local function clipOfTrack(track: AnimationTrack, meta: any): string?
	local anim = track.Animation
	if anim and anim.Name ~= "" then
		local base = string.gsub(anim.Name, "_R15$", "")
		if meta[base] then
			return base
		end
	end
	local id = anim and anim.AnimationId
	if id and id ~= "" then
		for name, m in meta do
			if
				type(m) == "table"
				and m.root
				and (animationId(name, true) == id or animationId(name .. "_R15", true) == id)
			then
				return name
			end
		end
	end
	return nil
end

-- ROOT MOTION for a character this machine owns, whoever started the clip: a player's moves are played by the SERVER
-- (Moves), but the player's client owns the body - so the client watches its Animator and moves the root for every
-- one-shot with a root track (StarterPlayerScripts.KitClient.AnimRoot calls this for the local character; review
-- 2026-10-16: server-only root motion never ran for players). Returns the connection.
function Anim.watchRootMotion(character: Model): RBXScriptConnection?
	local humanoid = character:FindFirstChildOfClass("Humanoid") or character:WaitForChild("Humanoid", 10)
	if not humanoid or not humanoid:IsA("Humanoid") then
		return nil
	end
	local animator = humanoid:FindFirstChildOfClass("Animator") or humanoid:WaitForChild("Animator", 10)
	if not animator or not animator:IsA("Animator") then
		return nil
	end
	return (animator :: Animator).AnimationPlayed:Connect(function(track: AnimationTrack)
		local meta: any = Anim.meta()
		local name = clipOfTrack(track, meta)
		local m = name and meta[name]
		if m and m.root and not m.loop then
			applyRoot(humanoid, track, m)
		end
		-- an authored CAMERA track (D9): the owning client drives its own camera, whoever started the clip
		if m and type(m.camera) == "table" and #m.camera > 0 then
			cameraTrack(humanoid, track, m.camera)
		end
		-- the CAMERA KICK (AAA gaps v2 D9): on the Hit the camera jumps along the blade's direction and springs back
		-- (Humanoid.CameraOffset, the owning client's own camera only)
		local kick = m and m.camera_kick
		if type(kick) == "table" and type(kick.dir) == "table" and RunService:IsClient() then
			local hum = humanoid :: Humanoid
			local dir = Vector3.new(kick.dir[1] or 0, kick.dir[2] or 0, kick.dir[3] or 0)
			local amp = tonumber(kick.amp) or 0.2
			local hitConn: RBXScriptConnection? = nil
			if kicked[track] then
				return -- (this track is hooked already: the same track played again must not kick twice)
			end
			kicked[track] = true
			hitConn = Anim.marker(track, "Hit", m.events):Connect(function()
				local t0 = os.clock()
				-- (ONE kick a camera at a time, laid ON TOP of whatever the camera's offset is: a second Hit inside
				-- the first kick's 0.3 s took the kicked offset for the camera's own and left it there for good - 9
				-- built clips have two Hits that close; and an offset the game sets meanwhile is the game's to keep)
				local kicking = kicks[hum]
				if not kicking then
					kicking = { delta = Vector3.zero, turn = 0 }
					kicks[hum] = kicking
				end
				kicking.turn += 1
				local mine = kicking.turn
				local run: RBXScriptConnection? = nil
				run = RunService.RenderStepped:Connect(function()
					local t = os.clock() - t0
					if kicking.turn ~= mine then -- (a later Hit took the camera over: it hands it back)
						if run then
							run:Disconnect()
						end
						return
					end
					local now = if t > 0.3 or not hum.Parent then Vector3.zero else dir * AnimLayers.kick(t, amp)
					hum.CameraOffset += now - kicking.delta
					kicking.delta = now
					if t > 0.3 or not hum.Parent then
						kicks[hum] = nil
						if run then
							run:Disconnect()
						end
					end
				end)
			end)
			track.Stopped:Once(function()
				if hitConn then
					hitConn:Disconnect()
				end
				kicked[track] = nil
			end)
		end
	end)
end

-- a TELEPORT (the owner's katana set, 2026-10-18: "he fades away and teleports"): a clip whose events include "Vanish"
-- fades the character out on that marker and back in on "Appear" (the travel in between is its root track); played
-- where the clip is played - Moves plays a player's moves on the server, so the fade replicates to everyone
local VANISH_FADE, APPEAR_FADE = 0.08, 0.06
-- the HAZE before a teleport (the owner, 2026-10-18: "he hazes and then teleports above"): from a "Haze" marker until
-- "Vanish" the character flickers between two see-through levels every HAZE_STEP seconds
local HAZE_STEP, HAZE_THIN, HAZE_THICK = 0.04, 0.6, 0.2

local function vanishOnMarkers(owner: Instance, track: AnimationTrack, clipMeta: any, enteredAt: number?)
	local events = clipMeta and clipMeta.events
	local has = false
	if type(events) == "table" then
		for _, e in events do
			if type(e) == "table" and (e.name == "Vanish" or e.name == "Haze") then
				has = true
			end
		end
	end
	if not has then
		return
	end
	local character = if owner:IsA("Humanoid") or owner:IsA("AnimationController") then owner.Parent else owner
	if not character then
		return
	end
	local TweenService = game:GetService("TweenService")
	local saved: { [Instance]: number } = {}
	local hazing = false
	local function parts(): { Instance }
		local out: { Instance } = {}
		for _, d in character:GetDescendants() do
			local isPart = d:IsA("BasePart") and d.Name ~= "HumanoidRootPart"
			if isPart or d:IsA("Decal") then
				table.insert(out, d)
				if saved[d] == nil then
					saved[d] = (d :: any).Transparency
				end
			end
		end
		return out
	end
	local function fade(out: boolean)
		hazing = false
		for _, d in parts() do
			if out then
				TweenService:Create(d, TweenInfo.new(VANISH_FADE), { Transparency = 1 }):Play()
			elseif saved[d] ~= nil then
				TweenService:Create(d, TweenInfo.new(APPEAR_FADE), { Transparency = saved[d] }):Play()
			end
		end
		if not out then
			table.clear(saved)
		end
	end
	local function haze()
		hazing = true
		local thin = true
		task.spawn(function()
			while hazing and track.IsPlaying do
				for _, d in parts() do
					local base = saved[d] or 0
					local item: any = d
					item.Transparency = math.min(1, base + (if thin then HAZE_THIN else HAZE_THICK))
				end
				thin = not thin
				task.wait(HAZE_STEP)
			end
		end)
	end
	local onHaze = Anim.marker(track, "Haze", events):Connect(haze)
	local onVanish = Anim.marker(track, "Vanish", events):Connect(function()
		fade(true)
	end)
	local onAppear = Anim.marker(track, "Appear", events):Connect(function()
		fade(false)
	end)
	-- a clip ENTERED past its Vanish and before its Appear (pose / distance matching jumps over markers): the body
	-- is gone there - the state the skipped marker would have set
	if enteredAt and enteredAt > 0 then
		local gone = AnimMarks.lastSkipped(events, "Vanish", enteredAt)
		local back = AnimMarks.lastSkipped(events, "Appear", enteredAt)
		if gone and not (back and back.t >= gone.t) then
			fade(true)
		else
			local hazed = AnimMarks.lastSkipped(events, "Haze", enteredAt)
			if hazed and not (back and back.t >= hazed.t) then
				haze() -- (entered between the Haze and the Vanish: it is hazing)
			end
		end
	end
	track.Stopped:Once(function()
		fade(false) -- never leave the character invisible or flickering (an interrupted teleport)
		onHaze:Disconnect()
		onVanish:Disconnect()
		onAppear:Disconnect()
	end)
end

-- FACE + AFTERIMAGE markers (AAA gaps v2 D10 / D12): a clip event "Face" (value = an image id) swaps the R6 face
-- decal on that beat - a glare on the wind-up, a shout on the hit - and is put back when the clip stops;
-- "Afterimage" (value = seconds, default 0.25) leaves fading copies of the body every AFTER_STEP s (a dash, a
-- flash-step). Played where the clip is played (Moves: the server) so everyone sees them.
local AFTER_STEP, AFTER_LIFE = 0.035, 0.22
local SMEAR_LIFE = 0.06 -- a smear slab lives a frame or two (B6)

local function effectsOnMarkers(
	owner: Instance,
	track: AnimationTrack,
	clipMeta: any,
	drawOnly: boolean?,
	enteredAt: number?
)
	local events = clipMeta and clipMeta.events
	local face, ghost, smear = false, false, false
	if type(events) == "table" then
		for _, e in events do
			if type(e) == "table" then
				face = face or e.name == "Face"
				ghost = ghost or e.name == "Afterimage"
				smear = smear or e.name == "Smear"
			end
		end
	end
	-- the face decal swap replicates from where the clip plays; the GHOSTS and SMEARS are drawn by every client itself
	-- (made on the server they replicated late and behind the arm - review 2026-10-22): Anim.watchEffects
	if drawOnly then
		face = false
	end
	if ghost or smear then
		if not RunService:IsClient() or drawn[track] then
			ghost, smear = false, false
		else
			drawn[track] = true
		end
	end
	if not (face or ghost or smear) then
		return
	end
	local character = if owner:IsA("Humanoid") or owner:IsA("AnimationController") then owner.Parent else owner
	if not character then
		return
	end
	local conns: { RBXScriptConnection } = {}
	local saved: string? = nil
	local decal: Decal? = nil
	if face then
		local head = character:FindFirstChild("Head")
		local d = head and head:FindFirstChildOfClass("Decal")
		if d then
			decal = d
			saved = d.Texture
			table.insert(
				conns,
				Anim.marker(track, "Face", events):Connect(function(value: string?)
					if value and value ~= "" then
						d.Texture = if string.find(value, "^%d+$") then "rbxassetid://" .. value else value
					end
				end)
			)
			-- (entered past a Face marker: the face the clip had put on by then)
			local worn = if enteredAt and enteredAt > 0 then AnimMarks.lastSkipped(events, "Face", enteredAt) else nil
			local image = if worn and worn.value ~= nil then tostring(worn.value) else ""
			if image ~= "" then
				d.Texture = if string.find(image, "^%d+$") then "rbxassetid://" .. image else image
			end
		end
	end
	if ghost then
		table.insert(
			conns,
			Anim.marker(track, "Afterimage", events):Connect(function(value: string?)
				local untilT = os.clock() + (tonumber(value) or 0.25)
				task.spawn(function()
					while os.clock() < untilT and track.IsPlaying and character.Parent do
						for _, p in character:GetChildren() do
							if p:IsA("BasePart") and p.Name ~= "HumanoidRootPart" and p.Transparency < 1 then
								local g = Instance.new("Part")
								g.Anchored, g.CanCollide, g.CanQuery, g.CanTouch, g.CastShadow =
									true, false, false, false, false
								g.Size, g.CFrame = p.Size, p.CFrame
								g.Material = Enum.Material.Neon
								g.Color = Color3.fromRGB(150, 205, 255)
								g.Transparency = 0.55
								g:SetAttribute("KitEffect", "afterimage") -- (what it is, for a probe or a cleanup)
								g.Parent = workspace
								game:GetService("TweenService")
									:Create(g, TweenInfo.new(AFTER_LIFE), { Transparency = 1 })
									:Play()
								game:GetService("Debris"):AddItem(g, AFTER_LIFE + 0.05)
							end
						end
						task.wait(AFTER_STEP)
					end
				end)
			end)
		)
	end
	if smear then
		-- SMEARS (AAA gaps v2 B6; "Smear" = "<part>,<part>;<seconds>"): an R6 part cannot stretch, so each frame of
		-- the window lays a MOTION SLAB per part - the part's box stretched (in its own axes) over the way it travelled
		-- since the last frame, in its own colour, gone in a frame or two: the smear frame of 2D animation
		table.insert(
			conns,
			Anim.marker(track, "Smear", events):Connect(function(value: string?)
				local spec = string.split(value or "", ";")
				local names = string.split(if spec[1] and spec[1] ~= "" then spec[1] else "Right Arm", ",")
				local untilT = os.clock() + (tonumber(spec[2]) or 0.05)
				local parts: { BasePart } = {}
				for _, d in character:GetDescendants() do
					if d:IsA("BasePart") and table.find(names, d.Name) and d.Transparency < 1 then
						table.insert(parts, d)
					end
				end
				local last: { [BasePart]: CFrame } = {}
				for _, p in parts do
					last[p] = p.CFrame
				end
				local conn: RBXScriptConnection? = nil
				conn = RunService.Heartbeat:Connect(function()
					if os.clock() > untilT or not character.Parent then
						if conn then
							conn:Disconnect()
						end
						return
					end
					for _, p in parts do
						local prev, cur = last[p], p.CFrame
						last[p] = cur
						local d = cur:VectorToObjectSpace(cur.Position - prev.Position)
						if d.Magnitude < 0.15 then
							continue -- (barely moving: no smear)
						end
						local g = Instance.new("Part")
						g.Anchored, g.CanCollide, g.CanQuery, g.CanTouch, g.CastShadow =
							true, false, false, false, false
						g.Size = p.Size + Vector3.new(math.abs(d.X), math.abs(d.Y), math.abs(d.Z))
						g.CFrame = prev:Lerp(cur, 0.5)
						g.Color, g.Material, g.Transparency = p.Color, p.Material, 0.35
						g:SetAttribute("KitEffect", "smear")
						g.Parent = workspace
						game:GetService("TweenService")
							:Create(g, TweenInfo.new(SMEAR_LIFE), { Transparency = 1 })
							:Play()
						game:GetService("Debris"):AddItem(g, SMEAR_LIFE + 0.02)
					end
				end)
			end)
		)
	end
	track.Stopped:Once(function()
		if decal and saved then
			decal.Texture = saved -- never leave a shouting face on an idle body
		end
		for _, c in conns do
			c:Disconnect()
		end
	end)
end

-- INERTIALIZATION (AAA gaps v2 D1; Bollo, GDC 2018): the new clip starts at once (no cross-fade) and the difference
-- from the old pose decays to nothing over `blend` seconds on a quintic - every Motor6D's Transform gets the offset
-- after the Animator wrote it (RunService.Stepped runs after the animation step)
local function motorsOf(character: Instance): { Motor6D }
	local out: { Motor6D } = {}
	for _, d in character:GetDescendants() do
		if d:IsA("Motor6D") then
			table.insert(out, d)
		end
	end
	return out
end

-- THE POSE A FRAME BEFORE, for the blend's starting speed (the owner's V3 list, anim stage F.1; AnimLayers.offsetRate):
-- a body that has played one inertialized clip has the clean pose of each joint kept for the last two frames
-- (Stepped, after the Animator wrote them). Its first such clip starts still (nothing kept yet), as before.
type TrailSample = { t: number, cf: CFrame }
local trails: { [Instance]: { [Motor6D]: { TrailSample } } } = setmetatable({}, { __mode = "k" }) :: any
local trailConn: RBXScriptConnection? = nil
local function trailStart(character: Instance)
	if trails[character] then
		return
	end
	trails[character] = {}
	if trailConn then
		return
	end
	trailConn = RunService.Stepped:Connect(function()
		local now = time() -- (the clock Anim.play reads too)
		for body, joints in trails do
			if not body.Parent then
				trails[body] = nil
				continue
			end
			for _, m in motorsOf(body) do
				local kept = joints[m] or {}
				joints[m] = kept
				local last = kept[#kept]
				if not last or last.t < now then
					table.insert(kept, { t = now, cf = layerClean(m) })
					if #kept > 2 then
						table.remove(kept, 1)
					end
				end
			end
		end
	end)
end
-- the joint's clean pose from the latest frame BEFORE now that is not the pose now (a play before this frame's
-- Stepped reads last frame's pose as "now": the sample before that one is its frame before; nil: none kept)
local function trailBefore(character: Instance, m: Motor6D, now: number, cur: CFrame): TrailSample?
	local kept = trails[character] and (trails[character] :: any)[m]
	if not kept then
		return nil
	end
	for i = #kept, 1, -1 do
		local k = kept[i]
		if k.t < now - 1e-4 and not (i > 1 and sameCF(k.cf, cur)) then
			return k
		end
	end
	return nil
end
local function twistOf(d: CFrame, axis: Vector3): number
	local ax, a = d:ToAxisAngle()
	local s = math.sin(a / 2)
	return AnimLayers.twist(ax.X * s, ax.Y * s, ax.Z * s, math.cos(a / 2), axis.X, axis.Y, axis.Z)
end

local function inertialize(character: Instance, before: { [Motor6D]: CFrame }, blend: number, beforeAt: number?)
	local started: number? = nil
	local offsets: { [Motor6D]: { axis: Vector3, angle: number, pos: Vector3, rate: number } } = {}
	local mem: LayerMem = {} -- (one of the layers on a joint: it shares their record, see layerBase)
	local conn: RBXScriptConnection? = nil
	conn = RunService.Stepped:Connect(function(frame: number)
		local now = os.clock()
		local first = not started
		if not started then
			started = now
			for m, old in before do
				if m.Parent then
					-- old = d * new, both the CLIP's poses: what the new clip plays is the clean value under any layer
					-- (measured against the joint as it stands, a look-at's turn was blended in twice)
					layerBase(m, mem, frame)
					local new = AnimLayers.stackOf(m).clean or m.Transform
					local d = old * new:Inverse()
					local axis, angle = d:ToAxisAngle()
					if math.abs(angle) > 1e-4 or d.Position.Magnitude > 1e-4 then -- (a joint that did not change: left alone)
						-- its speed: the same offset a frame before, read along this offset's axis
						local prev = if beforeAt then trailBefore(character, m, beforeAt, old) else nil
						local rate = if prev
							then AnimLayers.offsetRate(
								angle,
								twistOf(prev.cf * new:Inverse(), axis),
								(beforeAt :: number) - prev.t
							)
							else 0
						offsets[m] = { axis = axis, angle = angle, pos = d.Position, rate = rate }
					end
				end
			end
		end
		local t = now - (started :: number)
		if t >= blend or not character.Parent then
			if conn then
				conn:Disconnect()
			end
			layerRelease(mem)
			return
		end
		for m, o in offsets do
			if m.Parent then
				local a = AnimLayers.inertial(o.angle, o.rate, blend, t)
				local k = if math.abs(o.angle) > 1e-6 then a / o.angle else AnimLayers.inertial(1, 0, blend, t)
				local base = if first then (AnimLayers.stackOf(m).clean or m.Transform) else layerBase(m, mem, frame)
				layerWrite(m, mem, CFrame.new(o.pos * k) * CFrame.fromAxisAngle(o.axis, a) * base)
			end
		end
	end)
end

-- LOOK-AT (AAA gaps v2 D5): the head turns toward a target ON TOP of whatever clip plays (an offset on the Neck's
-- Transform after the Animator wrote it), spring-smoothed and clamped to a neck's reach. Returns a stop function.
-- ATTENTION BEYOND THE HEAD (the owner's older list, AN-30; the rules: AnimLayers.lookSplit / lookWeight / lookPermit):
--   body      the share of the turn the TORSO takes (0, the default: the head alone; 0.3 reads well). R6 has no
--             waist: the whole torso turns on its RootJoint and each hip turns and slides back by as much, so
--             the legs and the feet stay where they stood
--   maxBody   degrees the torso may turn (20)
--   permit    () -> 0..1, may the body look now. Default: not while a move has COMMITTED (Moves takes the
--             Humanoid's AutoRotate for the active frames of a move that says `track`), nor ragdolled, nor
--             seated. Not permitted, the look HOLDS where it is (it neither follows nor swings back) and goes on
--             when it may again. A game whose AutoRotate is off for another reason (a lock-on) passes its own.
-- The look is laid OVER the clip: a torso the clip has twisted keeps its twist (the head turns that much less).
-- The returned stop() eases the look out before it lets the joints go; stop(true) lets go at once.
-- A target BEHIND the body is not craned at: the look fades out past what head and body reach together.
-- target may be a function: what to look at NOW (a part, a point, or nil for nothing) - Anim.attention uses it.
-- A HELD GUN AT REST follows the look too: src/kit/AnimAim.barrel (its own layer on the joints' one record).
export type LookOptions = {
	maxYaw: number?,
	maxPitch: number?,
	halflife: number?,
	body: number?,
	maxBody: number?,
	permit: (() -> number)?,
}
export type LookTarget = BasePart | Vector3 | (() -> (BasePart | Vector3)?)

function Anim.lookAt(character: Model, target: LookTarget, opts: LookOptions?): (immediate: boolean?) -> ()
	local o: LookOptions = opts or {}
	local torso = character:FindFirstChild("Torso")
	if not torso or not torso:IsA("BasePart") then
		return function() end
	end
	local neck = torso:FindFirstChild("Neck")
	if not neck or not neck:IsA("Motor6D") then
		return function() end
	end
	local motor = neck :: Motor6D
	local body = torso :: BasePart
	local hum = character:FindFirstChildOfClass("Humanoid")
	-- the torso's own joint and the hips (R6): only when the body takes a share
	local rootPart = character:FindFirstChild("HumanoidRootPart")
	local found = if (o.body or 0) > 0 and rootPart then rootPart:FindFirstChild("RootJoint") else nil
	local rootJoint: Motor6D? = if found and found:IsA("Motor6D") then found else nil
	local hips: { Motor6D } = {}
	if rootJoint then
		for _, name in { "Left Hip", "Right Hip" } do
			local h = body:FindFirstChild(name)
			if h and h:IsA("Motor6D") then
				table.insert(hips, h)
			end
		end
	end
	local mem: LayerMem = {}
	local yawS: AnimFeel.Spring = { x = 0, v = 0 }
	local pitchS: AnimFeel.Spring = { x = 0, v = 0 }
	local bodyS: AnimFeel.Spring = { x = 0, v = 0 }
	local stopped = false
	local leaving: number? = nil -- (when the stop was asked for: the look eases out, then lets go)
	local conn: RBXScriptConnection
	local function finish()
		if not stopped then
			stopped = true
			conn:Disconnect()
			layerRelease(mem)
		end
	end
	conn = RunService.Stepped:Connect(function(frame: number, dt: number)
		if stopped then -- (a handler still called after its stop would join the joint again for good)
			return
		end
		if not motor.Parent or not character.Parent then
			finish() -- (the body is gone: nothing keeps running on it)
			return
		end
		local now: (BasePart | Vector3)? = if leaving
			then nil
			elseif type(target) == "function" then target()
			else target
		local bodyWant, headWant, pitchWant, permit = 0, 0, 0, 1
		-- the torso's joint as the clip (and any layer before this one) has it THIS frame, before this layer's turn
		local joint = if rootJoint
				and rootJoint.Parent
				and rootPart
				and rootPart:IsA("BasePart")
			then rootJoint
			else nil
		local rootWas: CFrame? = if joint then layerBase(joint, mem, frame) else nil
		local neckWas = layerBase(motor, mem, frame)
		if now then
			local at = if typeof(now) == "Vector3" then now :: Vector3 else (now :: BasePart).Position
			-- the HEAD as the clip has it this frame, before this layer's turn: the torso (un-looked) carrying the neck's
			-- own pose. The way to the target is measured from the BODY's facing (the root part: the look does not
			-- take a wind-up's twist back) and the head then turns what is left FROM WHERE THE CLIP HAS IT - a clip
			-- that turns the head itself is laid over, the gaze still lands (measured from the torso alone, a cut
			-- that had turned the head 34 degrees back left the gaze 36 degrees short, and over-turned it for a
			-- target straight ahead: seen in Studio)
			local unTorso = if joint and rootWas
				then (rootPart :: BasePart).CFrame * joint.C0 * rootWas * joint.C1:Inverse()
				else body.CFrame
			local relH = (unTorso * motor.C0 * neckWas * motor.C1:Inverse()):PointToObjectSpace(at)
			local yawH, pitch = AnimLayers.lookRaw(relH.X, relH.Y, relH.Z)
			local yaw, twist = yawH, 0
			if rootPart and rootPart:IsA("BasePart") then
				local relR = rootPart.CFrame:PointToObjectSpace(at)
				yaw = (AnimLayers.lookRaw(relR.X, relR.Y, relR.Z))
				twist = math.atan2(math.sin(yaw - yawH), math.cos(yaw - yawH))
			end
			bodyWant, headWant, pitchWant =
				AnimLayers.lookSplit(yaw, pitch, if joint then o.body else 0, o.maxBody, o.maxYaw, o.maxPitch, twist)
			permit = if o.permit
				then o.permit()
				elseif hum then AnimLayers.lookPermit(hum.AutoRotate, hum.PlatformStand, hum.Sit)
				else 1
			permit = if permit == permit then math.clamp(permit, 0, 1) else 0
		end
		if now and permit <= 0 then
			-- NOT PERMITTED (a move has committed): the look HOLDS where it is - it does not swing after the target
			-- and it does not swing back either (eased to nothing, the head swept 20 degrees through the hit)
			yawS.v, pitchS.v, bodyS.v = 0, 0, 0
		else
			local half = if leaving then 0.05 else (o.halflife or 0.12)
			yawS = AnimFeel.spring(yawS, headWant * permit, half, dt)
			pitchS = AnimFeel.spring(pitchS, pitchWant * permit, half, dt)
			bodyS = AnimFeel.spring(bodyS, bodyWant * permit, half * 1.5, dt) -- (the body is heavier than the head)
		end
		-- a turn in the torso's frame, carried into the joint's own frame through its C0
		local r = CFrame.Angles(0, yawS.x, 0) * CFrame.Angles(pitchS.x, 0, 0)
		local c0 = motor.C0.Rotation
		layerWrite(motor, mem, (c0:Inverse() * r * c0) * neckWas)
		if joint and rootWas then
			local rc0 = joint.C0.Rotation
			local rootNow = (rc0:Inverse() * CFrame.Angles(0, bodyS.x, 0) * rc0) * rootWas
			layerWrite(joint, mem, rootNow)
			for _, h in hips do
				if h.Parent then
					-- (each leg kept where it stands, whatever the clip has done to the torso: AnimLayers.keepLeg)
					local keep = AnimLayers.keepLeg(joint.C0, joint.C1, rootWas, rootNow, h.C0)
					layerWrite(h, mem, keep * layerBase(h, mem, frame))
				end
			end
		end
		if leaving then
			local still = math.abs(yawS.x) < 0.01 and math.abs(pitchS.x) < 0.01 and math.abs(bodyS.x) < 0.01
			if still or os.clock() - leaving > 0.5 then
				finish()
			end
		end
	end)
	-- stop(): the look eases out (a twentieth of a second's halflife) and then lets the joints go - let go at a full
	-- turn, head and torso jumped back in one frame. stop(true): at once.
	return function(immediate: boolean?)
		if immediate or stopped then
			finish()
		else
			leaving = leaving or os.clock()
		end
	end
end

-- WHAT A BODY ATTENDS TO (AN-30: "behavior-level targets ... authored priority"): several things it could look at,
-- each with a priority; it looks at the highest (of equals, the one named last - AnimLayers.attention), and the
-- look moves on its spring when that changes. Options are Anim.lookAt's.
--   local attend = Anim.attention(character, { body = 0.3 })
--   attend:set("door", doorPart, 1)   attend:set("threat", enemy.Head, 5)   attend:clear("threat")   attend:stop()
export type Attention = {
	set: (self: Attention, key: string, target: BasePart | Vector3, priority: number?) -> (),
	clear: (self: Attention, key: string) -> (),
	stop: (self: Attention) -> (),
}

function Anim.attention(character: Model, opts: LookOptions?): Attention
	local list: { [string]: { priority: number, since: number } } = {}
	local targets: { [string]: BasePart | Vector3 } = {}
	local named = 0
	local stop = Anim.lookAt(character, function(): (BasePart | Vector3)?
		while true do
			local key = AnimLayers.attention(list)
			if not key then
				return nil
			end
			local t = targets[key]
			if t and (typeof(t) ~= "Instance" or (t :: BasePart):IsDescendantOf(game)) then
				return t
			end
			-- (the thing it looked at is gone: the next one down is looked at, it does not stare at nothing)
			list[key] = nil
			targets[key] = nil
		end
	end, opts)
	local attend = {}
	function attend.set(_self: Attention, key: string, target: BasePart | Vector3, priority: number?)
		named += 1
		list[key] = { priority = priority or 0, since = named }
		targets[key] = target
	end
	function attend.clear(_self: Attention, key: string)
		list[key] = nil
		targets[key] = nil
	end
	function attend.stop(_self: Attention)
		stop()
	end
	return attend :: any
end

-- ADDITIVE LAYER (AAA gaps v2 D3): a clip built with `additive` (kit anim writes its change from a base frame into
-- Meta) laid OVER whatever plays - a flinch over an attack, breathing over the guard: every Motor6D's Transform becomes
-- Transform * delta(t) after the Animator wrote it, faded in / out. Returns a stop function (a one-shot stops itself).
-- SEEN BY EVERYONE (V4 4.4 / 13.4.3, card txjy): a joint's pose does not travel between machines, so on the SERVER
-- a clip's additive is also written as a cue on the character (AnimRules.additiveCue, attribute KitAdd_<clip>) and
-- every client's watcher (src/kit/client/AnimRoot.client: Anim.watchAdditive) plays it there, from where it is by
-- now; stop() writes the stop cue. at: seconds already in (a late watcher); observe: play it on a body this machine
-- does not own (the watcher's own call - it is what makes the layer show there)
export type AdditiveOptions = {
	weight: number?,
	speed: number?,
	loop: boolean?,
	fadeIn: number?,
	fadeOut: number?,
	at: number?,
	observe: boolean?,
}

export type AdditiveTrack = { times: { number }, joints: { [string]: { string } } }

-- `clip` = a clip name (its Meta `additive` track) or a track itself (code-made: breathing, a procedural flinch)
function Anim.additive(character: Model, clip: string | AdditiveTrack, opts: AdditiveOptions?): () -> ()
	local o: AdditiveOptions = opts or {}
	local m: any = if type(clip) == "string" then Anim.meta()[clip] else nil
	local track: any = if type(clip) == "string" then m and m.additive else clip
	if type(track) ~= "table" or type(track.times) ~= "table" or type(track.joints) ~= "table" then
		warn(`[Anim] additive: {clip} has no additive track (mark its clip "additive" and run kit anim)`)
		return function() end
	end
	-- the cue every client plays it from (a clip by name, started on the server)
	local cue = if RunService:IsServer() then AnimRules.cueName(clip) else nil
	local cued = false
	if cue then
		local loop0 = if o.loop ~= nil then o.loop else (m ~= nil and m.loop == true)
		local value = AnimRules.additiveCue(workspace:GetServerTimeNow() - (o.at or 0), o.weight, o.speed, loop0)
		if value then
			character:SetAttribute(cue, value)
			cued = true
		end
	end
	local function uncue()
		if cued and cue and character.Parent then
			cued = false
			character:SetAttribute(cue, AnimRules.stopCue(workspace:GetServerTimeNow()))
		end
	end
	if not owns(character) and not o.observe then
		-- (Transform writes only show on the machine that writes them: the clients play the cue)
		return uncue
	end
	local times: { number } = track.times
	local mem: LayerMem = {}
	local motors: { [Motor6D]: { CFrame } } = {}
	for _, motor in motorsOf(character) do
		local rows = motor.Part1 and track.joints[motor.Part1.Name]
		if type(rows) == "table" then
			local cfs: { CFrame } = {}
			for _, row in rows do
				local v = string.split(row, " ")
				local n = function(i: number): number
					return tonumber(v[i]) or 0
				end
				-- (Roblox's CFrame.new takes the quaternion as x, y, z, w after the position)
				table.insert(cfs, CFrame.new(n(5), n(6), n(7), n(1), n(2), n(3), n(4)))
			end
			motors[motor] = cfs
		end
	end
	local loop = if o.loop ~= nil then o.loop else (m ~= nil and m.loop == true)
	local length = if loop then math.huge else (times[#times] - times[1]) / (o.speed or 1)
	local weight, speed = o.weight or 1, o.speed or 1
	local at = if type(o.at) == "number" and o.at == o.at and o.at > 0 then math.min(o.at, 1e6) else 0
	local started = os.clock() - at -- (a late watcher: from where the layer is by now)
	local conn: RBXScriptConnection? = nil
	local stopping: number? = nil
	conn = RunService.Stepped:Connect(function(frame: number)
		local t = os.clock() - started
		local w = weight * AnimLayers.layerWeight(t, length, o.fadeIn or 0.06, o.fadeOut or 0.12)
		if stopping then
			w *= math.clamp(1 - (os.clock() - stopping) / (o.fadeOut or 0.12), 0, 1)
		end
		if t >= length or w <= 0 and stopping or not character.Parent then
			if conn then
				conn:Disconnect()
				layerRelease(mem)
			end
			return
		end
		local i, j, f = AnimLayers.sampleAt(times, times[1] + t * speed, loop)
		for motor, cfs in motors do
			if motor.Parent then
				local d = cfs[i]:Lerp(cfs[j], f)
				layerWrite(motor, mem, layerBase(motor, mem, frame) * CFrame.new():Lerp(d, w))
			end
		end
	end)
	return function()
		stopping = stopping or os.clock()
		uncue()
	end
end

-- THE WATCHER OF THE CUES (every client, for every character it shows: src/kit/client/AnimRoot.client): each
-- KitAdd_<clip> cue the server wrote on `character` is played here (Anim.additive, observe) from where it is by now,
-- and stopped by its stop cue; a cue already there when the watch begins is played too (a late joiner). Returns a
-- function that stops the watch and every layer it started.
function Anim.watchAdditive(character: Model): () -> ()
	local running: { [string]: () -> () } = {}
	local function cueChanged(name: string)
		if string.sub(name, 1, #AnimRules.CUE_PREFIX) ~= AnimRules.CUE_PREFIX then
			return
		end
		local clip = string.sub(name, #AnimRules.CUE_PREFIX + 1)
		local c = AnimRules.readCue(character:GetAttribute(name), workspace:GetServerTimeNow())
		local was = running[clip]
		if was then
			running[clip] = nil
			was()
		end
		if type(c) == "table" then
			running[clip] = Anim.additive(
				character,
				clip,
				{ weight = c.weight, speed = c.speed, loop = c.loop, at = c.at, observe = true }
			)
		end
	end
	for name in character:GetAttributes() do
		cueChanged(name)
	end
	local conn = character.AttributeChanged:Connect(cueChanged)
	return function()
		conn:Disconnect()
		for clip, stop in running do
			running[clip] = nil
			stop()
		end
	end
end

-- AUTHORED CAMERA (AAA gaps v2 D9): a finisher's own camera (Meta `camera`: keys in the character's starting root
-- space) drives the local player's camera while the track plays - read off the track's TimePosition, so a hit-stop
-- holds the shot too - then hands the camera back. Only on the client that owns the body (never another player's)
-- the camera's own state is saved ONCE while any track holds it (a second track takes over and the camera is handed
-- back once, when the last one ends - two overlapping tracks left it Scriptable for good: review 2026-10-22)
local camHold: { cameraType: Enum.CameraType, fov: number, token: {} }? = nil

cameraTrack = function(owner: Instance, track: AnimationTrack, keys: { any })
	local character = if owner:IsA("Humanoid") or owner:IsA("AnimationController") then owner.Parent else owner
	if not character or not RunService:IsClient() or not owns(character) or cammed[track] then
		return
	end
	cammed[track] = true
	local root = character:FindFirstChild("HumanoidRootPart")
	local cam = workspace.CurrentCamera
	if not root or not root:IsA("BasePart") or not cam then
		return
	end
	local start = (root :: BasePart).CFrame
	local token = {}
	if camHold then
		camHold.token = token
	else
		camHold = { cameraType = cam.CameraType, fov = cam.FieldOfView, token = token }
	end
	cam.CameraType = Enum.CameraType.Scriptable
	local conn: RBXScriptConnection? = nil
	local function finish()
		if conn then
			conn:Disconnect()
			conn = nil
			local hold = camHold
			if hold and hold.token == token then -- (a newer track took over: it hands the camera back)
				cam.CameraType, cam.FieldOfView = hold.cameraType, hold.fov
				camHold = nil
			end
		end
	end
	conn = RunService.RenderStepped:Connect(function()
		if not track.IsPlaying or not character.Parent or not camHold or camHold.token ~= token then
			finish()
			return
		end
		local loc, target, fov = AnimLayers.cameraAt(keys, track.TimePosition)
		local p = start:PointToWorldSpace(Vector3.new(loc[1], loc[2], loc[3]))
		local q = start:PointToWorldSpace(Vector3.new(target[1], target[2], target[3]))
		local dir = q - p
		-- (looking straight down / up: lookAt's default up is degenerate - use the character's facing)
		local up = if dir.Magnitude > 1e-6 and math.abs(dir.Unit.Y) > 0.999 then start.LookVector else Vector3.yAxis
		cam.CFrame = CFrame.lookAt(p, q, up)
		if fov then
			cam.FieldOfView = fov
		end
	end)
	track.Stopped:Once(finish)
end

-- the GHOSTS and SMEARS of every character, drawn by this client (AnimRoot.client binds every player's character)
function Anim.watchEffects(character: Model): RBXScriptConnection?
	if not RunService:IsClient() then
		return nil
	end
	local humanoid = character:FindFirstChildOfClass("Humanoid") or character:WaitForChild("Humanoid", 10)
	if not humanoid or not humanoid:IsA("Humanoid") then
		return nil
	end
	local animator = humanoid:FindFirstChildOfClass("Animator") or humanoid:WaitForChild("Animator", 10)
	if not animator or not animator:IsA("Animator") then
		return nil
	end
	return (animator :: Animator).AnimationPlayed:Connect(function(track: AnimationTrack)
		local meta: any = Anim.meta()
		local name = clipOfTrack(track, meta)
		local m = name and meta[name]
		if m then
			effectsOnMarkers(humanoid, track, m, true)
		end
	end)
end

export type PlayOptions = {
	enter: string?, -- "pose": start at the frame nearest the pose the character is in (the clip's `match` pose table)
	distance: number?, -- studs still to travel to the stop: start at the frame that far from it (its distance table)
	inertial: number?, -- blend seconds: inertialize from the current pose instead of cross-fading (~0.15-0.25)
	target: BasePart?, -- the motion-warp target (the clip's `warp` window travels / turns toward it)
}

-- MOTION MATCHING (the owner's method lists 2026-11-13; the search: AnimMatch.motionStep, spec'd and held to the
-- build's): a MOTION SET (assets/animations/motion/<Set>.motion.json, baked by `kit anim` into KitAnimations.Motion)
-- is played by looking, a few times a second, for the frame of ANY of its clips that best continues what the body
-- is doing - its pose now and how each joint turned since the frame before. While the body follows the clip being
-- played, that clip simply runs on; when another clip's motion fits better (the body was pushed, came out of a
-- ragdoll, a layer bent it), the set cross-fades to that clip at that frame. A clip is never scrubbed within itself;
-- a clip that does not loop plays its last frames out and the set then goes to its REST (the set's looping clip).
--   local stop = Anim.motion(humanoid, "Guard", { every = 0.1, fade = 0.15, start = "Idle" })
-- WHERE TO CALL IT: on the client that shows the character (a joint's pose is read off THIS machine). R6 only.
-- STEERING (the owner's limitations list 2026-11-15, A-R02): { steer = true } hands the search where the player wants
-- to go - the Humanoid's MoveDirection at its WalkSpeed, seen from the way the body faces - so a start, a stop or a
-- change of direction picks the clip that GOES there, not only the one that continues the pose. steer may be a
-- function -> { vx, vz, turn } (the body's own frame, -Z ahead; an NPC's path, a lock-on) or nil for "nothing asked".
-- turnIn: the seconds in which the body is to face the way it goes (left out: it keeps its facing).
-- only: a function -> { [clip] = true }, the clips the game allows now (stunned: no attack; in the air: no step).
-- A move in flight is not steered, and steering never starts a move (a clip that does not loop is offered under an
-- ask only when `only` names it). With the Humanoid's AutoRotate on, where the body goes counts as AHEAD (strafe and
-- back clips are for a body that keeps its facing: AutoRotate off, a lock-on).
-- Without steer the set only continues motion, as before.
-- Studio-unproven (written 2026-11-14; steering 2026-11-15).
export type MotionOptions = {
	every: number?,
	fade: number?,
	start: string?,
	steer: (boolean | () -> { number }?)?,
	turnIn: number?,
	only: (() -> { [string]: boolean }?)?,
}

-- the motion sets' databases written by kit anim, or {} when none was built
function Anim.motionSets(): { [string]: AnimMatch.MotionDb }
	local folder = ReplicatedStorage:FindFirstChild("KitAnimations")
	local module = folder and folder:FindFirstChild("Motion")
	if module and module:IsA("ModuleScript") then
		local ok, sets = pcall(require, module)
		if ok and type(sets) == "table" then
			return sets
		end
	end
	return {}
end

function Anim.motion(owner: Instance, setName: string, opts: MotionOptions?): () -> ()
	local o: MotionOptions = opts or {}
	local db = Anim.motionSets()[setName]
	local character = if owner:IsA("Humanoid") or owner:IsA("AnimationController") then owner.Parent else owner
	if not db or not character then
		warn(`[Anim] no motion set "{setName}" (assets/animations/motion/{setName}.motion.json -> lune run kit anim)`)
		return function() end
	end
	local body = Anim.poseOf(character)
	for _, joint in db.joints do
		if not body[joint] then
			warn(`[Anim] motion set {setName}: this body has no {joint} (the set's clips are R6's)`)
			return function() end
		end
	end
	local tracks: { [string]: AnimationTrack } = {}
	for name in db.clips do
		local track = Anim.load(owner, name)
		if not track then
			warn(`[Anim] motion set {setName}: its clip {name} is not in the game`)
			return function() end
		end
		tracks[name] = track
	end
	local every, fade = o.every or 0.1, o.fade or 0.15
	local steerHum = character:FindFirstChildOfClass("Humanoid")
	local steerPart = character:FindFirstChild("HumanoidRootPart")
	local steerRoot: BasePart? = if steerPart and steerPart:IsA("BasePart") then steerPart else nil
	local okC, Crowd = pcall(function()
		return (require :: any)(script.Parent:FindFirstChild("AnimCrowd"))
	end)
	local rest: string = if db.rest and tracks[db.rest] then db.rest else next(tracks) :: string
	local playing: string = if o.start and tracks[o.start] then o.start else rest
	tracks[playing]:Play(fade)
	local function go(name: string, frame: number?)
		if name ~= playing then
			tracks[playing]:Stop(fade)
			playing = name
		end
		tracks[name]:Play(fade)
		if frame then
			tracks[name].TimePosition = frame / db.fps
		end
	end
	-- a look takes two frames in a row: the pose, then the pose one frame later (how it is turning NOW, not over
	-- the whole wait: the database's rows were made the same way)
	local before: { [string]: { number } }? = nil
	local waited = 0
	local conn = RunService.Stepped:Connect(function(_, dt: number)
		if not tracks[playing].IsPlaying then
			go(rest) -- (a clip that does not loop has played out)
			before, waited = nil, 0
			return
		end
		waited += dt
		if before then
			local pose = Anim.poseOf(character)
			local current = { playing :: any, tracks[playing].TimePosition * db.fps }
			local want: { number }? = nil
			if type(o.steer) == "function" then
				want = (o.steer :: () -> { number }?)()
			elseif o.steer == true and steerHum and steerRoot then
				-- (Anim.going, not MoveDirection alone: a body walked by MoveTo is asked nothing and still goes)
				local move, look = Anim.going(steerHum), steerRoot.CFrame.LookVector
				if steerHum.AutoRotate and move.Magnitude > 1e-3 then
					-- (the engine turns the body to the way it goes: where it goes IS ahead - judged against the
					-- facing of this instant, a reversal would pick the back clip and drop it again as the body turns)
					look = move
				end
				want = AnimMatch.wanted(move.X, move.Z, look.X, look.Z, steerHum.WalkSpeed, o.turnIn)
			end
			local name, frame, jump =
				AnimMatch.motionStep(db, before, pose, dt, current, want, if o.only then o.only() else nil)
			before, waited = nil, 0
			if jump and name ~= playing then
				go(name, frame) -- (only BETWEEN clips: a clip is never scrubbed within itself)
			end
		elseif waited >= every and not (okC and Crowd and not Crowd.due(character)) then
			before = Anim.poseOf(character)
		end
	end)
	return function()
		conn:Disconnect()
		for _, track in tracks do
			track:Stop(fade)
			track:Destroy()
		end
	end
end

-- PROCEDURAL FOOT PLACEMENT (the owner's method lists 2026-11-13; the rule: AnimRules.feet / feetStep, spec'd): an R6
-- body's feet meet the ground they are over - a ray under each foot reads its height, the pelvis drops and each leg
-- slides in its hip (a one-piece leg does not bend), eased so nothing snaps at a step's edge; in the air the offsets
-- ease back to the clip's own. Written after the Animator like every kit layer.
-- WHERE TO CALL IT: on each CLIENT, for every character it shows - a joint's pose does not travel between machines,
-- so feet placed on the server are seen by nobody (there it only moves what the server's hit checks read). With many
-- characters, track them in src/kit/AnimCrowd: a far one is placed every 2nd or 4th frame, or not at all.
--   local stop = Anim.feet(character, { rate = 12, limits = { drop = 1, lift = 1.2, reach = 0.3 } })
-- Studio-unproven (written 2026-11-14).
-- CONTACT STATE (2026-11-15, the owner's limitations list A-R03; the rule: AnimRules.stance / stanceStep, spec'd): each
-- foot is planted, in its swing or unsupported, read off how far the CLIP holds its sole above its floor - only
-- planted feet carry the pelvis; a sole stands on the highest ground under it (the ray's normal); a planted foot is
-- led by how fast its ground moves relative to the body (a lift, a moving platform); limits.tilt (degrees, default 0)
-- lets the pelvis lean with the ground. { contact = false } keeps the first rule (heights only).
export type FeetOptions = {
	rate: number?,
	plantedRate: number?,
	contact: boolean?,
	limits: AnimRules.StanceLimits?,
}

function Anim.feet(character: Model, opts: FeetOptions?): () -> ()
	local o: FeetOptions = opts or {}
	local hum = character:FindFirstChildOfClass("Humanoid")
	local rootPart = character:FindFirstChild("HumanoidRootPart")
	if not hum or not rootPart or not rootPart:IsA("BasePart") then
		return function() end
	end
	local legs: { [string]: Motor6D } = {}
	local pelvisMotor: Motor6D? = nil
	for _, m in motorsOf(character) do
		if m.Part1 and (m.Part1.Name == "Left Leg" or m.Part1.Name == "Right Leg") then
			legs[m.Part1.Name] = m
		elseif m.Part0 == rootPart and m.Part1 and m.Part1.Name == "Torso" then
			pelvisMotor = m
		end
	end
	local left, right = legs["Left Leg"], legs["Right Leg"]
	if not left or not right or not pelvisMotor then
		return function() end -- (not an R6 body: nothing to place)
	end
	local pelvis: Motor6D = pelvisMotor
	local okC, Crowd = pcall(function()
		return (require :: any)(script.Parent:FindFirstChild("AnimCrowd"))
	end)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { character }
	params.RespectCanCollide = true -- (ground is what a foot can stand on: not a trigger box, a hitbox, an effect)
	params.IgnoreWater = true
	local mem: LayerMem = {}
	local cur = { 0, 0, 0, 0, 0 }
	local stateL: string?, stateR: string? = nil, nil
	local waited = 0
	local root = rootPart :: BasePart
	-- a foot as the contact rule reads it: the ground under its sole (height, normal in the body's frame, how fast it
	-- moves relative to the body) and how far the clip holds the sole above its floor (this layer's own slide taken out)
	local function sample(m: Motor6D, slide: number): AnimRules.Sample
		local leg = m.Part1 :: BasePart
		local floorY = root.Position.Y - (hum.HipHeight + root.Size.Y / 2 + leg.Size.Y)
		local sole = leg.CFrame * Vector3.new(0, -leg.Size.Y / 2, 0)
		-- (the sole's LOWEST edge: a one-piece leg swung 30 degrees has its sole's middle 0.27 up and its toe on
		-- the floor - read at the middle, every angled stance leg was "in its swing")
		local low = sole.Y
			- (leg.Size.X / 2) * math.abs(leg.CFrame.RightVector.Y)
			- (leg.Size.Z / 2) * math.abs(leg.CFrame.LookVector.Y)
		local out: AnimRules.Sample = { height = 0 / 0, lifted = low - floorY - slide }
		local hit = workspace:Raycast(Vector3.new(sole.X, floorY + 3, sole.Z), Vector3.new(0, -6, 0), params)
		if hit then
			local n = root.CFrame:VectorToObjectSpace(hit.Normal)
			out.height, out.nx, out.ny, out.nz = hit.Position.Y - floorY, n.X, n.Y, n.Z
		end
		-- the ground under the sole's toe and heel (a step is under the toe before it is under the middle)
		local look = root.CFrame.LookVector
		local ahead = Vector3.new(look.X, 0, look.Z)
		if ahead.Magnitude > 1e-3 then
			ahead = ahead.Unit * (leg.Size.Z / 2 - 0.05)
			local more, slopes = {}, {}
			for _, at in { sole + ahead, sole - ahead } do
				local edge = workspace:Raycast(Vector3.new(at.X, floorY + 3, at.Z), Vector3.new(0, -6, 0), params)
				table.insert(more, if edge then edge.Position.Y - floorY else 0 / 0)
				table.insert(slopes, if edge then math.deg(math.acos(math.clamp(edge.Normal.Y, -1, 1))) else 0)
			end
			out.more, out.moreSlope = more, slopes
		end
		return out
	end
	-- each foot's ground height at the last look while it was planted (AnimRules.groundRate: a moving support)
	local lastL: number?, lastR: number? = nil, nil
	-- the ground's height under a foot, above (+) or below (-) the floor the body stands on; NaN = none found
	local function under(m: Motor6D): number
		local leg = m.Part1 :: BasePart
		local floorY = root.Position.Y - (hum.HipHeight + root.Size.Y / 2 + leg.Size.Y)
		local sole = leg.CFrame * Vector3.new(0, -leg.Size.Y / 2, 0)
		local hit = workspace:Raycast(Vector3.new(sole.X, floorY + 3, sole.Z), Vector3.new(0, -6, 0), params)
		return if hit then hit.Position.Y - floorY else 0 / 0
	end
	-- the Animator's pose slid along the PARENT part's up (Part1 = Part0 * C0 * Transform * C1^-1: a slide put in
	-- FRONT of the Transform is in C0's axes, so the body's up there is C0's turn undone)
	local stamp = 0 -- (this frame's number, for the layers' shared record)
	local function slid(m: Motor6D, studs: number): CFrame
		return CFrame.new(m.C0.Rotation:Inverse() * Vector3.new(0, studs, 0)) * layerBase(m, mem, stamp)
	end
	local function write()
		for i, m in { pelvis, left, right } do
			local to = slid(m, cur[i])
			if cur[4] ~= 0 or cur[5] ~= 0 then
				-- the lean, about the body's own right (pitch) and ahead (roll) axes, in the joint's axes like the
				-- slide; each HIP turns the other way by as much, so the legs stay upright under a leaning body
				-- (leaning them too swung both soles half a stud across the floor)
				local c0 = m.C0.Rotation
				local lean = CFrame.Angles(cur[4], 0, cur[5])
				to = (c0:Inverse() * (if i == 1 then lean else lean:Inverse()) * c0) * to
			end
			layerWrite(m, mem, to)
		end
	end
	local ended = false
	local conn = RunService.Stepped:Connect(function(frame: number, dt: number)
		if ended then
			return
		end
		stamp = frame
		waited += dt
		if okC and Crowd and not Crowd.due(character) then
			write() -- not this character's frame: its last offsets stand
			return
		end
		-- in the air (a jump, a fall, a ragdoll) there is no ground to meet: back to the clip's own
		local state = hum:GetState()
		local air = hum.FloorMaterial == Enum.Material.Air
			or state == Enum.HumanoidStateType.Freefall
			or state == Enum.HumanoidStateType.Jumping
			or state == Enum.HumanoidStateType.Swimming
			or state == Enum.HumanoidStateType.PlatformStanding
		if o.contact == false then
			local hl = if air then 0 / 0 else under(left)
			local hr = if air then 0 / 0 else under(right)
			local three = AnimRules.feetStep(cur, hl, hr, waited, o.rate, o.limits) -- (the time since it was last placed)
			cur = { three[1], three[2], three[3], 0, 0 }
		else
			local none: AnimRules.Sample = { height = 0 / 0, lifted = math.huge } -- (in the air: both feet swing)
			local sl = if air then none else sample(left, cur[1] + cur[2])
			local sr = if air then none else sample(right, cur[1] + cur[3])
			-- (the ground the SOLE stands on - toe, middle or heel - not the middle's alone: a foot the toe already
			-- lifted onto a step must not be "led" again when its middle crosses the edge)
			local groundL = (AnimRules.soleGround(sl, if o.limits then o.limits.sole else nil, o.limits))
			local groundR = (AnimRules.soleGround(sr, if o.limits then o.limits.sole else nil, o.limits))
			sl.vy = AnimRules.groundRate(lastL, groundL, waited)
			sr.vy = AnimRules.groundRate(lastR, groundR, waited)
			local want = AnimRules.stance(sl, sr, stateL, stateR, o.limits)
			stateL, stateR = want.stateLeft, want.stateRight
			lastL = if stateL == "planted" then groundL else nil
			lastR = if stateR == "planted" then groundR else nil
			cur = AnimRules.stanceStep(cur, want, sl, sr, waited, o.rate, o.plantedRate)
		end
		waited = 0
		write()
	end)
	return function()
		ended = true
		conn:Disconnect()
		layerRelease(mem)
	end
end

-- the pose a character is in, as the kit's clips say a pose ({ [part] = { x, y, z, w } }, each part's turn in its
-- parent's space at rest): what AnimMatch.poseFrame takes. Studio-unproven (written 2026-11-14).
function Anim.poseOf(character: Instance): { [string]: { number } }
	local out: { [string]: { number } } = {}
	for _, motor in motorsOf(character) do
		if motor.Part1 then
			-- (C1's turn: on R6 it is C0's at rest, and the kit's lean tilts C0, never C1)
			local c = motor.C1.Rotation
			local axis, angle = (c * motor.Transform.Rotation * c:Inverse()):ToAxisAngle()
			local s = math.sin(angle / 2)
			out[motor.Part1.Name] = { axis.X * s, axis.Y * s, axis.Z * s, math.cos(angle / 2) }
		end
	end
	return out
end

-- where to ENTER a clip, in seconds, from its match tables (Meta.<name>.match, baked by `kit anim` for a clip that
-- says "match"): by the pose given (pose matching) or by the studs still to travel (distance matching). nil = the
-- clip carries no such table (it is played from its start). Pure: no instances.
function Anim.enterTime(clipMeta: any, pose: { [string]: { number } }?, distance: number?): (number?, string?)
	return AnimMatch.enterTime(clipMeta, pose, distance)
end

function Anim.play(
	owner: Instance,
	name: string,
	fadeTime: number?,
	weight: number?,
	speed: number?,
	opts: PlayOptions?
): AnimationTrack?
	local o: PlayOptions = opts or {}
	local track = Anim.load(owner, name)
	if track then
		local character = if owner:IsA("Humanoid") or owner:IsA("AnimationController") then owner.Parent else owner
		local before: { [Motor6D]: CFrame }? = nil
		local beforeAt = time()
		if o.inertial and o.inertial > 0 and character then
			before = {}
			for _, m in motorsOf(character) do
				(before :: any)[m] = layerClean(m) -- (the pose the old clip played, not a layer's write on top of it)
			end
			trailStart(character) -- (from now on its poses are kept: the next blend starts at the speed it moved)
		end
		track:Play(if before then 0 else (fadeTime or 0.1), weight or 1, speed or 1)
		if before and character then
			inertialize(character, before, o.inertial :: number, beforeAt)
		end
		local m = (Anim.meta() :: any)[name]
		local entered: number? = nil
		if m and character and (o.enter == "pose" or o.distance) then
			-- POSE / DISTANCE MATCHING: entered where its tables say (a clip with no table starts at 0 and says so)
			local at, why = Anim.enterTime(m, if o.enter == "pose" then Anim.poseOf(character) else nil, o.distance)
			if at then
				track.TimePosition = at
				entered = at
				AnimMarks.entered(marksOf(track).state, at) -- (the markers before it are not owed)
			else
				warn(
					if why == "no shared joint"
						then `[Anim] {name}: this body has none of its pose table's joints (an R15 body on an R6 clip?) - played from its start`
						else `[Anim] {name} carries no match table for that (say "match" in its move and run kit anim)`
				)
			end
		end
		if m and m.root and not m.loop then
			applyRoot(owner, track, m, o.target, entered)
		end
		if m then
			vanishOnMarkers(owner, track, m, entered)
			effectsOnMarkers(owner, track, m, nil, entered)
			if type(m.camera) == "table" and #m.camera > 0 then
				cameraTrack(owner, track, m.camera)
			end
		end
	end
	return track
end

-- the clips' metadata written by kit anim (ground speeds, durations, events, feel), or {} when not built
function Anim.meta(): AnimBlend.Meta
	local folder = ReplicatedStorage:FindFirstChild("KitAnimations")
	local module = folder and folder:FindFirstChild("Meta")
	if module and module:IsA("ModuleScript") then
		local ok, meta = pcall(require, module)
		if ok and type(meta) == "table" then
			return meta
		end
	end
	return {}
end

-- ---------------------------------------------------------------- locomotion
export type Locomotion = { stop: (self: Locomotion) -> () }

-- Drive a character's locomotion with the kit's clips: every frame the move direction (in the character's space)
-- and ground speed pick the weights (AnimBlend) and rates (feet matched to the real speed through each clip's
-- ground speed); Jumping / Freefall / Landed play the set's one-shots. Roblox's own Animate script is disabled
-- while this runs and handed back on :stop(). Call on the CLIENT for the local player's character (the animations
-- replicate), on the server for NPCs.
-- options.lean: tilt the body into its acceleration at runtime (AnimFeel.lean: true = the defaults, or its params),
-- on the R6 RootJoint's C0 (handed back on :stop()).
export type LocomotionOptions = { lean: (boolean | AnimFeel.LeanParams)? }

function Anim.locomotion(character: Model, set: AnimBlend.Set, options: LocomotionOptions?): Locomotion
	local humanoid = character:FindFirstChildOfClass("Humanoid") :: Humanoid
	assert(humanoid, "[Anim] locomotion needs a character with a Humanoid")
	assert(set.idle, "[Anim] locomotion needs an idle clip in its set (what plays when the character stands)")
	local root = humanoid.RootPart or (character:FindFirstChild("HumanoidRootPart") :: BasePart?)
	local meta = Anim.meta()
	local animate = character:FindFirstChild("Animate")
	if animate and animate:IsA("LocalScript") then
		animate.Disabled = true
	end
	local animator = animatorOf(humanoid)
	if animator then
		for _, t in animator:GetPlayingAnimationTracks() do
			t:Stop(0)
		end
	end
	local flow = AnimBlend.flow() -- (the moments between the loops: AnimBlend.transition)
	-- a moment's clip: ONE track a clip (loaded once), at Movement priority (a built clip is an Action: it would cut
	-- across an attack), the moment before it stopped, none while an attack plays, no root travel of its own;
	-- entered at the pose the body is in when the clip carries a pose table
	local moments: { [string]: AnimationTrack } = {}
	local lastMoment: AnimationTrack? = nil
	local function busy(): boolean
		if not animator then
			return false
		end
		for _, t in animator:GetPlayingAnimationTracks() do
			local p = t.Priority
			local action = p == Enum.AnimationPriority.Action
				or p == Enum.AnimationPriority.Action2
				or p == Enum.AnimationPriority.Action3
				or p == Enum.AnimationPriority.Action4
			if action then
				return true
			end
		end
		return false
	end
	local function playMoment(name: string)
		if busy() then
			return
		end
		local track = moments[name]
		if not track then
			local loaded = Anim.load(humanoid, name)
			if not loaded then
				return
			end
			loaded.Priority = Enum.AnimationPriority.Movement
			loaded.Looped = false
			moments[name] = loaded
			track = loaded
		end
		local before = lastMoment
		if before and before ~= track and before.IsPlaying then
			before:Stop(0.1)
		end
		track:Play(0.08, 1, 1)
		local m = (meta :: any)[name]
		if m and type(m.match) == "table" and m.match.pose ~= nil then
			local at = Anim.enterTime(m, Anim.poseOf(character), nil)
			if at then
				track.TimePosition = at
			end
		end
		lastMoment = track
	end
	local lastFacing = if root then select(2, root.CFrame:ToOrientation()) else 0
	local loops: { [string]: AnimationTrack } = {}
	for _, key in { "idle", "walk", "run", "back", "strafeLeft", "strafeRight", "fall" } do
		local name = (set :: any)[key]
		if type(name) == "string" and not loops[name] then
			local track = Anim.load(humanoid, name)
			if track then
				track.Priority = Enum.AnimationPriority.Core
				track.Looped = true
				loops[name] = track
			end
		end
	end
	local connections: { RBXScriptConnection } = {}
	local leanOpt = options and options.lean
	local leanParams: AnimFeel.LeanParams? = if type(leanOpt) == "table" then leanOpt else nil
	local rootJoint = if leanOpt and root then root:FindFirstChild("RootJoint") else nil
	local baseC0 = if rootJoint and rootJoint:IsA("Motor6D") then rootJoint.C0 else nil
	local leanState = AnimFeel.newLean()
	local oneShots: { [string]: AnimationTrack } = {} -- jump / land, loaded once and replayed
	local falling = false
	local stopped = false
	local function stopAll()
		if stopped then
			return
		end
		stopped = true
		for _, c in connections do
			c:Disconnect()
		end
		for _, track in loops do
			track:Stop(0.1)
		end
		for _, track in oneShots do
			track:Stop(0.1)
		end
		for _, track in moments do
			track:Stop(0.1)
		end
		if rootJoint and baseC0 and rootJoint.Parent then
			local joint = rootJoint :: Motor6D
			joint.C0 = baseC0
		end
		if animate and animate:IsA("LocalScript") then
			animate.Disabled = false
		end
	end
	local function oneShot(name: string?)
		if not name then
			return
		end
		local t = oneShots[name]
		if not t then
			local loaded = Anim.load(humanoid, name)
			if not loaded then
				return
			end
			loaded.Priority = Enum.AnimationPriority.Movement
			oneShots[name] = loaded
			t = loaded
		end
		t:Play(0.05, 1, 1)
	end
	-- a dead or removed character hands itself back (nothing keeps running on a corpse or after a respawn)
	table.insert(connections, humanoid.Died:Connect(stopAll))
	table.insert(
		connections,
		character.AncestryChanged:Connect(function(_, parent)
			if parent == nil then
				stopAll()
			end
		end)
	)
	table.insert(
		connections,
		humanoid.StateChanged:Connect(function(_, new)
			-- (the rule: AnimBlend.falling / oneShot, spec'd)
			falling = AnimBlend.falling(new.Name)
			oneShot(AnimBlend.oneShot(set, new.Name))
		end)
	)
	table.insert(
		connections,
		RunService.Heartbeat:Connect(function(dt: number)
			if stopped or not root or not humanoid.Parent then
				return
			end
			local velocity = root.AssemblyLinearVelocity
			if rootJoint and baseC0 then
				-- the R6 RootJoint's C0 axes: local x = world -X (a + turn leans the torso FORWARD), local y = world +Z
				local localVel = root.CFrame:VectorToObjectSpace(velocity)
				local pitch, roll
				leanState, pitch, roll = AnimFeel.lean(leanState, localVel.X, localVel.Z, dt, leanParams)
				local joint = rootJoint :: Motor6D
				joint.C0 = baseC0 * CFrame.Angles(pitch, -roll, 0)
			end
			local speed = Vector3.new(velocity.X, 0, velocity.Z).Magnitude
			-- (Anim.going, not MoveDirection alone: under Humanoid:MoveTo the idle slid along at walking speed -
			-- seen in Studio, 2026-11-15)
			local localMove = root.CFrame:VectorToObjectSpace(Anim.going(humanoid))
			local wanted = AnimBlend.airborne(set, falling, AnimBlend.weights(set, meta, localMove, speed))
			-- THE MOMENTS BETWEEN THE LOOPS (AnimBlend.transition): a start, a stop, a pivot, a turn on the spot - a
			-- one-shot of the set laid over the blend. Read only while the body WALKS: on foot, at no more than one
			-- and a half times its WalkSpeed, its velocity taken over the floor it stands on - a flung body, a
			-- ragdoll, a rider and a body carried by a belt started and stopped (the one review, 2026-11-15)
			local _, facing = root.CFrame:ToOrientation()
			local turned = math.deg(math.atan2(math.sin(facing - lastFacing), math.cos(facing - lastFacing)))
			lastFacing = facing
			local over = velocity - floorVelocity(character, humanoid, root, velocity)
			local walking = not falling
				and AnimBlend.onFoot(humanoid:GetState().Name, humanoid.PlatformStand, humanoid.Sit)
				and Vector3.new(over.X, 0, over.Z).Magnitude <= 1.5 * math.max(humanoid.WalkSpeed, 1)
			local moment: string? = nil
			if walking then
				moment = AnimBlend.transition(flow, over.X, over.Z, turned / math.max(dt, 1e-3), dt, humanoid.WalkSpeed)
			else
				flow = AnimBlend.flow()
			end
			local between = if moment then (set :: any)[moment] else nil
			if type(between) == "string" then
				playMoment(between)
			end
			for name, track in loops do
				local play = wanted[name]
				if play then
					if not track.IsPlaying then
						track:Play(0.15, play.weight, play.rate)
					else
						track:AdjustWeight(play.weight, 0.12)
						track:AdjustSpeed(play.rate)
					end
				elseif track.IsPlaying then
					track:Stop(0.15)
				end
			end
		end)
	)
	local controller = {}
	function controller.stop(_self: Locomotion)
		stopAll()
	end
	return controller :: Locomotion
end

return Anim

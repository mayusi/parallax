-- Cutscene (ReplicatedStorage.kit.Cutscene) — play a kit cutscene in the game: the timeline kit/anim/cutscene.py
-- planned and rendered (`lune run kit anim cutscene <script> --game` -> KitAnimations.Cutscenes), on real R6 bodies.
--   local handle = Cutscene.play("KatanaDuel", anchor, { shade = npcA, ronin = npcB }, { idle = "Idle" })
--   handle.finished:Wait()
-- Each actor plays the kit's OWN clips (by name, from the planned point in them) with its root ANCHORED on the planned
-- path (anchor * the cutscene's space); every hit-stop freezes every track at once; an actor is hidden through its
-- teleport gaps; on a client the camera flies the planned keys inside letterbox bars and is handed back at the end.
-- Played where the bodies are owned (the server for NPCs everyone sees; a client for a local cinematic). In a game the
-- server plays the bodies and tells each client (a remote the game owns) to play it as a VIEWER - an empty cast: the
-- camera and the bars only, `startAt` = the seconds since the server started it, on the clock both share:
--   server: startedAt = workspace:GetServerTimeNow()  (sent with the remote)
--   client: Cutscene.play("KatanaDuel", anchor, {}, { startAt = workspace:GetServerTimeNow() - startedAt })
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local Anim = require(script.Parent:WaitForChild("Anim"))
local AnimPaired = require(script.Parent:WaitForChild("AnimPaired"))
local Rules = require(script.Parent:WaitForChild("CutsceneRules"))
-- the presentation event bus (src/kit/Bus), when the game has it: a cutscene's impacts are Hit / Parried events like a
-- fight's, so the game's sparks, sounds and shakes answer them without this module calling any of them
local Bus: any? = (function()
	local ok, mod = pcall(function()
		return (require :: any)(script.Parent:FindFirstChild("Bus"))
	end)
	return if ok then mod else nil
end)()

local Cutscene = {}

export type Options = {
	idle: string?, -- a KitAnimations clip played (looped) in the "@idle" spans; nil = the body's own pose
	camera: boolean?, -- client only: fly the planned camera (default true)
	letterbox: boolean?, -- client only: the cinema bars (default true)
	onEvent: ((ev: any) -> ())?, -- each planned event (impact / flash / streak, a hit-stop as "hitstop") as it passes
	ready: number?, -- seconds to wait for the clips to load before starting (default 3)
	manual: boolean?, -- no frame clock: handle.step(dt) moves the cutscene (scrubbing, replays, tests)
	startAt: number?, -- seconds into the cutscene to start from (a viewer joining a scene already running)
	bus: boolean?, -- false: do not publish the impacts as Hit / Parried on the kit Bus (default: publish)
	onStart: ((t: number) -> ())?, -- called when the clock really starts (after the clips load), with where it starts
	onFinish: (() -> ())?, -- called when it ends or is stopped (set before it starts: never missed, however fast)
	-- A PAIRED MOVE THAT CAN BE BROKEN OFF (src/kit/AnimPaired, the owner's older list AN-32). `breaks`: the rule
	-- (true: the defaults) - each frame every body is asked: gone, dead, stunned from outside (the combat code's
	-- stun, "KitStunnedUntil" on its model, read where the bodies are played: the server; or a game's own
	-- "KitStunned" = true), moved off the plan; the scene then ends - `onBreak` is told why, for whom, and what
	-- each body does ("release" | "stagger" | "fall" | "none"), BEFORE onFinish and `finished`; a broadcast scene
	-- tells its viewers to stop. Unsaid: nothing breaks it (as before).
	breaks: (AnimPaired.Rule | boolean)?,
	onBreak: ((verdict: AnimPaired.Verdict, exits: { [string]: string }) -> ())?,
	-- seconds since the SERVER started the scene, asked every frame (a viewer's `startAt`, kept current): a machine
	-- more than a tenth of a second off is put back on it
	clock: (() -> number)?,
}
export type Handle = {
	finished: RBXScriptSignal,
	stop: () -> (),
	time: () -> number,
	step: (dt: number) -> (), -- (manual mode only)
}

-- the planned timeline of a cutscene (nil when the game has none of that name)
function Cutscene.get(name: string): any?
	local folder = ReplicatedStorage:FindFirstChild("KitAnimations")
	local mod = folder and folder:FindFirstChild("Cutscenes")
	if not mod or not mod:IsA("ModuleScript") then
		return nil
	end
	local ok, all = pcall(require, mod)
	return if ok and type(all) == "table" then (all :: any)[name] else nil
end

local function letterbox(): (() -> ())?
	local Players = game:GetService("Players")
	local pg = Players.LocalPlayer and Players.LocalPlayer:FindFirstChildOfClass("PlayerGui")
	if not pg then
		return nil
	end
	local gui = Instance.new("ScreenGui")
	gui.Name = "_kit_cutscene_bars"
	gui.IgnoreGuiInset = true
	gui.DisplayOrder = 50
	gui.ResetOnSpawn = false
	local bars = {}
	for _, top in { true, false } do
		local f = Instance.new("Frame")
		f.Name = if top then "Top" else "Bottom"
		f.BackgroundColor3 = Color3.new(0, 0, 0)
		f.BorderSizePixel = 0
		f.AnchorPoint = Vector2.new(0, if top then 0 else 1)
		f.Position = UDim2.fromScale(0, if top then 0 else 1)
		f.Size = UDim2.fromScale(1, 0)
		f.Parent = gui
		table.insert(bars, f)
		TweenService:Create(f, TweenInfo.new(0.35, Enum.EasingStyle.Quad), { Size = UDim2.fromScale(1, 0.11) }):Play()
	end
	gui.Parent = pg
	return function()
		for _, f in bars do
			TweenService:Create(f, TweenInfo.new(0.3, Enum.EasingStyle.Quad), { Size = UDim2.fromScale(1, 0) }):Play()
		end
		task.delay(0.35, function()
			gui:Destroy()
		end)
	end
end

-- play the cutscene `name` with `cast` (actor name -> R6 Model) on `anchor` (the cutscene's origin: its +Y up, -Z
-- forward, at a standing HumanoidRootPart's height) -> a handle, or nil + why
function Cutscene.play(name: string, anchor: CFrame, cast: { [string]: Model }, opts: Options?): (Handle?, string?)
	local o: Options = opts or {}
	local tl = Cutscene.get(name)
	if not tl then
		return nil, `no cutscene "{name}" in KitAnimations.Cutscenes (lune run kit anim cutscene <script> --game)`
	end
	local fps = tonumber(tl.fps) or 30
	local duration = tonumber(tl.duration) or 0
	local hits: { Rules.Hit } = tl.hits or {}

	type Actor = {
		role: string,
		wrote: Vector3?, -- where the plan last put its root
		model: Model,
		hum: Humanoid,
		root: BasePart,
		spec: any,
		tracks: { [string]: AnimationTrack },
		idle: AnimationTrack?,
		seg: number?,
		current: AnimationTrack?,
		hidden: boolean,
		saved: { [Instance]: number },
		anchored: boolean,
	}
	local actors: { Actor } = {}
	for an, spec in tl.actors do
		local model = cast[an]
		local hum = model and model:FindFirstChildOfClass("Humanoid")
		local root = model and model:FindFirstChild("HumanoidRootPart")
		if model and hum and root and root:IsA("BasePart") then
			local a: Actor = {
				role = an,
				wrote = nil,
				model = model,
				hum = hum,
				root = root,
				spec = spec,
				tracks = {},
				idle = nil,
				seg = nil,
				current = nil,
				hidden = false,
				saved = {},
				anchored = root.Anchored,
			}
			-- every clip it plays, loaded up front (a clip's first load is async: started late, it would run short)
			for _, p in spec.plays or {} do
				if string.sub(p.clip, 1, 1) ~= "@" and not a.tracks[p.clip] then
					local tr = Anim.load(hum, p.clip)
					if tr then
						tr.Priority = Enum.AnimationPriority.Action4
						a.tracks[p.clip] = tr
					end
				end
			end
			if o.idle then
				local tr = Anim.load(hum, o.idle)
				if tr then
					tr.Looped = true
					a.idle = tr
				end
			end
			root.Anchored = true
			table.insert(actors, a)
		end
	end
	-- (a VIEWER: a client with no bodies of its own flies only the camera + bars while the server plays the bodies)
	local viewer = #actors == 0 and RunService:IsClient() and o.camera ~= false
	if #actors == 0 and not viewer then
		return nil, `cutscene "{name}": none of its actors is in the cast`
	end

	local done = Instance.new("BindableEvent")
	local stopped = false
	local t = math.clamp(tonumber(o.startAt) or 0, 0, duration) -- (a late joiner starts where everyone else is)
	local conn: RBXScriptConnection? = nil
	local camType: Enum.CameraType?, camFov: number? = nil, nil
	local unbars: (() -> ())? = nil
	local cam = workspace.CurrentCamera
	local useCam = RunService:IsClient() and o.camera ~= false and cam ~= nil and type(tl.camera) == "table"

	-- hidden through a teleport's gap: parts / decals / textures go transparent, trails / beams / emitters / highlights /
	-- billboards are switched off; re-applied every hidden frame (a part welded on mid-gap hides too) and put back
	-- exactly as they were
	local function setHidden(a: Actor, hide: boolean)
		if not hide and not a.hidden then
			return
		end
		a.hidden = hide
		if hide then
			for _, d in a.model:GetDescendants() do
				if a.saved[d] == nil then
					local v: any = d
					if d:IsA("BasePart") or d:IsA("Decal") or d:IsA("Texture") then
						a.saved[d] = v.Transparency
						v.Transparency = 1
					elseif
						d:IsA("Trail")
						or d:IsA("Beam")
						or d:IsA("ParticleEmitter")
						or d:IsA("Highlight")
						or d:IsA("BillboardGui")
						or d:IsA("SurfaceGui")
					then
						a.saved[d] = if v.Enabled then 1 else 0
						v.Enabled = false
					end
				end
			end
			return
		end
		for d, was in a.saved do
			if d.Parent then
				local v: any = d
				if d:IsA("BasePart") or d:IsA("Decal") or d:IsA("Texture") then
					v.Transparency = was
				else
					v.Enabled = was == 1
				end
			end
		end
		a.saved = {}
	end

	local function finish()
		if stopped then
			return
		end
		stopped = true
		if conn then
			conn:Disconnect()
		end
		for _, a in actors do
			setHidden(a, false)
			for _, tr in a.tracks do
				tr:Stop(0.2)
			end
			if a.idle then
				a.idle:Stop(0.2)
			end
			if a.root.Parent then
				a.root.Anchored = a.anchored
			end
			task.delay(0.3, function() -- (released after their fade: replays never pile tracks up on the Animator)
				for _, tr in a.tracks do
					tr:Destroy()
				end
				if a.idle then
					a.idle:Destroy()
				end
			end)
		end
		if useCam and cam and camType then
			cam.CameraType = camType
			cam.FieldOfView = camFov or cam.FieldOfView
		end
		if unbars then
			unbars()
		end
		if o.onFinish then
			task.spawn(o.onFinish)
		end
		done:Fire()
		task.defer(function()
			done:Destroy()
		end)
	end

	-- a track pinned on its frame `at` (held: speed 0) - never left to run out (a one-shot that reaches its end stops
	-- and the body falls back to its default pose)
	local function pin(tr: AnimationTrack, at: number)
		local last = if tr.Length > 0 then tr.Length - 1 / 60 else at
		tr.TimePosition = math.clamp(at, 0, last)
		if tr.Speed ~= 0 then
			tr:AdjustSpeed(0)
		end
	end

	-- the cast's order: the same on every machine (a tie between two bodies' breaks goes to the first)
	local order: { string } = {}
	for _, a in actors do
		table.insert(order, a.role)
	end
	table.sort(order)
	local breakRule: AnimPaired.Rule? = if type(o.breaks) == "table" then o.breaks elseif o.breaks then {} else nil
	-- a break ends the scene for everyone: every body is given back as it was before the scene (a body that was
	-- not anchored falls from where the plan held it), and the game is told what each one does
	local function broken(v: AnimPaired.Verdict)
		local exits: { [string]: string } = {}
		for _, a in actors do
			exits[a.role] = AnimPaired.exits(v, a.role)
		end
		if o.onBreak then
			task.spawn(o.onBreak, v, exits) -- (first: a game told of the end already knows it was a break)
		end
		finish()
	end
	-- the event cursors put where the time is (a clock that snapped: nothing between is fired in a burst, and what a
	-- rewind passed again is fired again when it comes)
	local seek: () -> ()

	local nextEvent, nextHit = 1, 1
	local events = tl.events or {}
	function seek()
		nextEvent, nextHit = 1, 1
		while nextEvent <= #events and events[nextEvent].t < t do -- (a late start does not fire what already happened)
			nextEvent += 1
		end
		while nextHit <= #hits and hits[nextHit].t < t do
			nextHit += 1
		end
	end
	seek()
	local function step(dt: number)
		t += dt
		if o.clock then
			-- (a clock that errors is no clock: this machine's own count stands)
			local ok, server = pcall(o.clock)
			local at, snapped = AnimPaired.resync(t, if ok and type(server) == "number" then server else nil)
			t = math.clamp(at, 0, duration)
			if snapped then
				seek()
			end
		end
		if breakRule then
			local facts: { [string]: AnimPaired.Facts } = {}
			for _, a in actors do
				local present = a.model.Parent ~= nil and a.root.Parent ~= nil
				local wrote = a.wrote
				facts[a.role] = {
					present = present,
					alive = a.hum.Health > 0,
					stunned = a.model:GetAttribute("KitStunned") == true or (RunService:IsServer() and (tonumber(
						a.model:GetAttribute("KitStunnedUntil")
					) or 0) > workspace:GetServerTimeNow()), -- (Moves writes it on its game clock)
					apart = if present and wrote then (a.root.Position - wrote).Magnitude else nil,
				}
			end
			local v = AnimPaired.verdict(breakRule, t, order, facts)
			if v then
				broken(v)
				return
			end
		end
		local frozen = Rules.inHitstop(hits, t)
		while nextEvent <= #events and events[nextEvent].t <= t do
			local ev = events[nextEvent]
			nextEvent += 1
			if o.onEvent then
				task.spawn(o.onEvent, ev)
			end
			-- (published where the bodies are - never by a viewer, so a hit is heard once - with `cutscene` naming it,
			-- damage 0: a listener that only wants fights can tell)
			if Bus and o.bus ~= false and not viewer and ev.type == "impact" then
				local p = ev.pos
				local at = if type(p) == "table"
					then anchor:PointToWorldSpace(Vector3.new(p[1], p[2], p[3]))
					else anchor.Position
				local victim = if ev.on then cast[ev.on] else nil
				Bus.publish(if ev.parry then "Parried" else "Hit", {
					attacker = if ev.by then cast[ev.by] else nil,
					victim = victim,
					damage = 0,
					move = name,
					at = at,
					weight = math.clamp((tonumber(ev.size) or 1) / 1.5, 0, 1),
					surface = if victim then victim:GetAttribute("KitSurface") or "flesh" else "flesh",
					cutscene = name,
				}, { near = 250 })
			end
		end
		while nextHit <= #hits and hits[nextHit].t <= t do
			if o.onEvent then
				task.spawn(o.onEvent, { t = hits[nextHit].t, type = "hitstop", hold = hits[nextHit].hold })
			end
			nextHit += 1
		end
		for _, a in actors do
			local x, y, z, yaw = Rules.rootAt(a.spec.root or {}, fps, t, nil, a.spec.jumps)
			a.root.CFrame = anchor * CFrame.new(x, y, z) * CFrame.Angles(0, yaw, 0)
			a.wrote = a.root.Position
			setHidden(a, Rules.hiddenAt(a.spec.hidden or {}, t))
			local plays = a.spec.plays or {}
			local i = Rules.segmentAt(plays, t)
			if i ~= a.seg then
				a.seg = i
				local p = if i then plays[i] else nil
				local tr = if p and string.sub(p.clip, 1, 1) ~= "@" then a.tracks[p.clip] else nil
				if p and p.clip == "@hold" then
					-- the clip it was playing stays on the planned last frame of that play
					local prev = if i and i > 1 then plays[i - 1] else nil
					if a.current and prev and prev.clip ~= "@idle" and prev.clip ~= "@hold" then
						pin(a.current, (prev.from or 0) + (prev.len or 0))
					end
				elseif p and (p.clip == "@idle" or not tr) then
					-- (a clip the game does not have - a library clip, an unloaded one - idles instead)
					if a.current then
						a.current:Stop(0.15)
						a.current = nil
					end
					if a.idle and not a.idle.IsPlaying then
						a.idle:Play(0.15)
					end
				elseif p and tr then
					if a.current and a.current ~= tr then
						a.current:Stop(math.max(0.02, p.fade or 0.05))
					end
					if a.idle and a.idle.IsPlaying then
						a.idle:Stop(math.max(0.02, p.fade or 0.05))
					end
					a.current = tr
					tr:Play(math.max(0.02, p.fade or 0.05), 1, 1)
					tr.TimePosition = Rules.trackTime(p, hits, t)
				end
			end
			local p = if a.seg then plays[a.seg] else nil
			local tr = a.current
			if tr and p and p.clip ~= "@hold" and p.clip ~= "@idle" then
				-- kept on the plan (a slow frame or a throttled machine lets a track drift), frozen in a hit-stop,
				-- pinned on its last frame when the plan runs it to (or past) the clip's end
				local want = Rules.trackTime(p, hits, t)
				if tr.Length > 0 and want >= tr.Length - 1 / 60 then
					pin(tr, want)
				else
					local speed = if frozen then 0 else 1
					if tr.Speed ~= speed then
						tr:AdjustSpeed(speed)
					end
					if math.abs(tr.TimePosition - want) > 0.08 then
						tr.TimePosition = want
					end
				end
			end
			if a.idle and a.idle.IsPlaying then -- (the hit-stop holds the idling body too)
				local speed = if frozen then 0 else 1
				if a.idle.Speed ~= speed then
					a.idle:AdjustSpeed(speed)
				end
			end
		end
		if useCam and cam then
			local loc, target = Rules.cameraAt(tl.camera, t, tl.cuts)
			local p = anchor:PointToWorldSpace(Vector3.new(loc[1], loc[2], loc[3]))
			local q = anchor:PointToWorldSpace(Vector3.new(target[1], target[2], target[3]))
			cam.CFrame = CFrame.lookAt(p, q)
		end
		if t >= duration then
			finish()
		end
	end

	local started = false
	local function start()
		if started or stopped then
			return
		end
		started = true
		if useCam and cam then
			camType, camFov = cam.CameraType, cam.FieldOfView
			cam.CameraType = Enum.CameraType.Scriptable
		end
		if RunService:IsClient() and o.letterbox ~= false then
			unbars = letterbox()
		end
		step(0)
		if o.onStart and not stopped then -- (a scene that broke on its first frame never started: nobody is told it did)
			task.spawn(o.onStart, t) -- (when the clock REALLY starts - after the clips loaded; t = where it starts)
		end
	end

	if not o.manual then
		-- wait (bounded) for the clips to load, then start on the frame clock
		local deadline = os.clock() + (o.ready or 3)
		task.spawn(function()
			while os.clock() < deadline do
				local all = true
				for _, a in actors do
					for _, tr in a.tracks do
						if tr.Length <= 0 then
							all = false
						end
					end
				end
				if all then
					break
				end
				task.wait()
			end
			start()
			if not stopped then
				conn = RunService.Heartbeat:Connect(step)
			end
		end)
	end

	return {
		finished = done.Event,
		stop = finish,
		time = function()
			return t
		end,
		-- manual mode: the caller moves the clock (a scrub in an editor, a replay, a test at the plan's own 60 fps)
		step = function(dt: number)
			if not o.manual or stopped then
				return
			end
			if not started then
				start()
			end
			step(dt)
		end,
	},
		nil
end

-- NETWORKED (2026-10-24): the server plays the bodies everyone sees and tells every client - and every player who joins
-- while it runs - to play it as a VIEWER (the camera + letterbox) from where the server is, on the clock both share.
-- One RemoteEvent the server fires and clients only listen to: no server handler exists, nothing to exploit.
Cutscene.REMOTE = "KitCutscene"

local function remote(create: boolean): RemoteEvent?
	local r = ReplicatedStorage:FindFirstChild(Cutscene.REMOTE)
	if not r and create then
		r = Instance.new("RemoteEvent")
		r.Name = Cutscene.REMOTE
		r.Parent = ReplicatedStorage
	end
	return if r and r:IsA("RemoteEvent") then r else nil
end

-- server: play `name` on `cast` and show it to every player (late joiners join where it is) -> the handle, or nil + why
function Cutscene.broadcast(name: string, anchor: CFrame, cast: { [string]: Model }, opts: Options?): (Handle?, string?)
	if not RunService:IsServer() then
		return nil, "Cutscene.broadcast runs on the server (clients: Cutscene.listen)"
	end
	local r = remote(true) :: RemoteEvent
	local o: any = table.clone((opts or {}) :: any)
	local startedAt: number? = nil
	local joined: RBXScriptConnection? = nil
	local userStart = o.onStart
	-- announced when the bodies' clock REALLY starts (play first waits for the clips to load - up to `ready` s: a viewer
	-- timed from the call ran ahead of the bodies; review 2026-10-24), on the clock both machines share
	o.onStart = function(t0: number)
		startedAt = workspace:GetServerTimeNow() - t0
		-- (also stamped on the remote while it runs: a client whose listener connects after this fire - its scripts
		-- loaded late - reads it there and joins where it is)
		r:SetAttribute("Name", name)
		r:SetAttribute("Anchor", anchor)
		r:SetAttribute("StartedAt", startedAt)
		r:FireAllClients(name, anchor, startedAt)
		joined = game:GetService("Players").PlayerAdded:Connect(function(p: Player)
			r:FireClient(p, name, anchor, startedAt)
		end)
		if userStart then
			userStart(t0)
		end
	end
	-- (cleaned up through onFinish, set BEFORE play: a scene that ends at once - startAt past its end - finishes inside
	-- play, before a finished:Once here could connect; review 2026-10-24)
	local userFinish = o.onFinish
	o.onFinish = function()
		if joined then
			joined:Disconnect()
		end
		if startedAt and r:GetAttribute("StartedAt") == startedAt then
			r:SetAttribute("Name", nil)
			r:SetAttribute("Anchor", nil)
			r:SetAttribute("StartedAt", nil)
		end
		if startedAt then
			-- the scene is over HERE - on time, stopped or broken: every viewer of this broadcast stops with it (a
			-- viewer left flying the planned camera over bodies already released; the one review, 2026-11-15)
			r:FireAllClients(name, nil, startedAt)
		end
		if userFinish then
			userFinish()
		end
	end
	local handle, why = Cutscene.play(name, anchor, cast, o)
	if not handle then
		return nil, why
	end
	return handle, nil
end

-- client: play every cutscene the server broadcasts as a viewer (`opts` = the viewer's options, e.g. { letterbox =
-- false }) -> the function that stops listening. ONE per client - the kit's AnimRoot client script already calls it in
-- every game, so a game calls it only to pass options (after stopping that one) or not at all
local listening = false -- (one listener per client: two would play two viewers fighting over one camera)
function Cutscene.listen(opts: Options?): () -> ()
	if not RunService:IsClient() or listening then
		return function() end -- (already listening - the kit's AnimRoot client script starts it in every game)
	end
	listening = true
	local base: Options = opts or {}
	local seen: { [number]: boolean } = {}
	local conn: RBXScriptConnection? = nil
	local stopped = false
	local current: Handle? = nil
	local currentStart: number? = nil
	local function join(name: any, anchor: any, startedAt: any)
		if type(name) == "string" and anchor == nil and type(startedAt) == "number" then
			-- the server's scene ended (it broke, was stopped, or ran out): this viewer's ends with it
			if current and currentStart == startedAt then
				current.stop()
				current, currentStart = nil, nil
			end
			seen[startedAt] = true
			return
		end
		if type(name) ~= "string" or typeof(anchor) ~= "CFrame" or type(startedAt) ~= "number" or seen[startedAt] then
			return
		end
		seen[startedAt] = true -- (the event and the stamp both announce one broadcast: joined once)
		-- ONE viewer at a time: a newer broadcast replaces the one playing (two would fight over the camera, and the
		-- later to finish would hand back the other's Scriptable camera - review 2026-10-24)
		if current then
			current.stop()
		end
		local o: any = table.clone(base :: any)
		-- a late observer joins where everyone is - or not at all, when it is over (AnimPaired.joinAt) - and is kept
		-- on the server's time while it plays (a client that hitched is snapped back, not left behind)
		local tl = Cutscene.get(name)
		local at = AnimPaired.joinAt(workspace:GetServerTimeNow() - startedAt, tonumber(tl and tl.duration) or 0)
		if not at then
			return
		end
		o.startAt = at
		o.clock = function(): number
			return workspace:GetServerTimeNow() - startedAt
		end
		current = Cutscene.play(name, anchor, {}, o)
		currentStart = if current then startedAt else nil
	end
	-- the remote appears with the server's first broadcast - maybe minutes in: wait for it as long as it takes, quietly
	-- (an untimed WaitForChild warns "infinite yield"), then hear every broadcast and join one already running
	task.spawn(function()
		local r = ReplicatedStorage:FindFirstChild(Cutscene.REMOTE)
		while not r and not stopped do
			local c = ReplicatedStorage.ChildAdded:Wait()
			if c.Name == Cutscene.REMOTE then
				r = c
			end
		end
		if stopped or not r or not r:IsA("RemoteEvent") then
			return
		end
		conn = (r :: RemoteEvent).OnClientEvent:Connect(join)
		join(r:GetAttribute("Name"), r:GetAttribute("Anchor"), r:GetAttribute("StartedAt"))
	end)
	return function()
		stopped = true
		listening = false
		if conn then
			conn:Disconnect()
		end
		if current then
			current.stop()
		end
	end
end

return Cutscene

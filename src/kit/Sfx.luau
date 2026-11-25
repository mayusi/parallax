--!strict
-- Sfx (ReplicatedStorage.kit.Sfx) — game sounds as EVENTS on Roblox's Audio API (AudioPlayer -> AudioEmitter ->
-- AudioListener per bus -> AudioFader per bus -> master -> AudioDeviceOutput). Data: assets/sounds/events.json
-- (synced as ReplicatedStorage.SfxEvents); resolution, voice limits and snapshots: SfxRules (pure, tested).
--   Sfx.play("SwordHit", { at = part | Vector3 | nil, surface = "metal", weight = 0.8, volume?, pitch? })
--       CLIENT: plays here (nil `at` = 2D: UI, music). SERVER: same as broadcast.
--   Sfx.broadcast("SwordHit", at, params?, except?)   SERVER: every client plays it; `except` (the attacker, who
--       already played it locally the moment they swung — client prediction) is skipped.
--   Sfx.snapshot("combat", seconds?)  CLIENT: blend the bus volumes to a snapshot (nil = back to base)
--   Sfx.setBus("music", 0.4)          CLIENT: a player setting (settings menu slider) -> that bus's fader
--   Sfx.stats() -> { voices, byBus, dropped }   for playtests (voice limits proven in the engine)
--   Sfx.reverb("HallStone" | nil)     CLIENT: the zone's reverb on the spatial sfx / voice buses (nil = dry)
--   Sfx.graph() -> { root, reverb, acoustic }   CLIENT: the built graph, for playtests
--   Sfx.voice(sound, opts?) -> handle           one voice on this graph for the kit's own modules (Music, Ambience,
--       WindVoice, GustEvents, EchoZones, Foley via Assets.play): bus, at, volume, pitch, looped, near, range, eq
--   Sfx.preload({ "SwordHit", ... }) -> loaded, wanted   fetch every take of those events' sounds ahead (yields)
-- Each bus has its own AudioInteractionGroup: an emitter on bus "sfx" is heard only by the "sfx" listener, so
-- faders, ducking and snapshots act per bus. Ducking ("duck": { bus, to, seconds }) dips another bus briefly.
-- The graph (SfxRules.graph, LIMITATIONS_FIXES_V4 SFX-X 7.3): acoustic simulation on every spatial emitter /
-- listener, an event's "directivity" as the emitter's AngleAttenuation, a pooled AudioReverb per spatial bus, the
-- music bus through a sidechain AudioCompressor keyed by sfx + voice, and a master AudioCompressor before the device.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local Workspace = game:GetService("Workspace")

local SfxRules = require("./SfxRules")

local Sfx = {}

local REMOTE_NAME = "SfxPlay"
local SPATIAL = { sfx = true, ambience = true, voice = true } -- ui + music play 2D (SfxRules.graph decides the same)

local catalog: any = { events = {} }
do
	local m = ReplicatedStorage:FindFirstChild("SfxEvents")
	if m and m:IsA("ModuleScript") then
		local ok, data = pcall(require, m)
		if ok and type(data) == "table" then
			catalog = data
		else
			warn("[Sfx] SfxEvents failed to load: " .. tostring(data))
		end
	end
end
local registry: any = {}
do
	local m = ReplicatedStorage:FindFirstChild("AssetIds")
	if m and m:IsA("ModuleScript") then
		local ok, data = pcall(require, m)
		if ok and type(data) == "table" then
			registry = data
		end
	end
end

local rng = Random.new()
local warned: { [string]: boolean } = {}
local function warnOnce(key: string, msg: string)
	if not warned[key] then
		warned[key] = true
		warn("[Sfx] " .. msg)
	end
end

-- a random take of a logical sound (name, name_2, name_3 ...) from assets/ids.json
local function takeId(name: string): string?
	local sounds = registry.sounds or {}
	local takes = {}
	local n = 1
	local key = name
	while sounds[key] do
		table.insert(takes, sounds[key])
		n += 1
		key = `{name}_{n}`
	end
	if #takes == 0 then
		warnOnce(name, `sound "{name}" has no uploaded id — upload build/sounds/{name}.ogg (lune run kit upload)`)
		return nil
	end
	return takes[rng:NextInteger(1, #takes)]
end

-- ---------------------------------------------------------------- the graph (client)
type Bus = { fader: AudioFader, listener: AudioListener?, base: number }
local buses: { [string]: Bus } = {}
local master: AudioFader? = nil
local active: { SfxRules.Voice } = {}
local players: { [number]: AudioPlayer } = {}
local lastStart: { [string]: number } = {}
local nextId = 0
local dropped = 0

local function wire(from: Instance, to: Instance, parent: Instance, targetPin: string?): Wire
	local w = Instance.new("Wire")
	w.SourceInstance = from
	w.TargetInstance = to
	if targetPin then
		w.TargetName = targetPin
	end
	w.Parent = parent
	return w
end

-- set an engine property that may not exist on this build (acoustic simulation is newer than the Audio API)
local function try(inst: Instance, prop: string, value: any): boolean
	return (pcall(function()
		(inst :: any)[prop] = value
	end))
end

local function setComp(c: Instance, s: { [string]: number })
	try(c, "Threshold", s.threshold)
	try(c, "Ratio", s.ratio)
	try(c, "Attack", s.attack)
	try(c, "Release", s.release)
	try(c, "MakeupGain", s.makeup)
end

local reverbs: { [string]: Instance } = {} -- one pooled AudioReverb per reverb bus (bypassed while dry)
local graphRoot: Folder? = nil
local acousticOn = false
local reverbName: string? = nil

local function buildGraph()
	if master then
		return
	end
	local plan = SfxRules.graph(catalog)
	local root = Instance.new("Folder")
	root.Name = "KitSfx"
	local out = Instance.new("AudioDeviceOutput")
	out.Parent = root
	local m = Instance.new("AudioFader")
	m.Name = "Master"
	m.Parent = root
	if next(plan.master) then
		-- master -> peak-catching compressor -> the device (SfxRules.MASTER_COMP: the standard values and why)
		local c = Instance.new("AudioCompressor")
		c.Name = "MasterComp"
		setComp(c, plan.master)
		c.Parent = root
		wire(m, c, root)
		wire(c, out, root)
	else
		wire(m, out, root)
	end
	local ducked: { [string]: Instance } = {}
	for _, d in plan.ducks do
		local c = Instance.new("AudioCompressor")
		c.Name = "Duck_" .. d.bus
		setComp(c, d.comp)
		c.Parent = root
		wire(c, m, root)
		ducked[d.bus] = c
	end
	for _, gb in plan.buses do
		local name = gb.name
		local f = Instance.new("AudioFader")
		f.Name = "Bus_" .. name
		f.Volume = gb.volume
		f.Parent = root
		-- a ducked bus reaches the master through its sidechain compressor
		wire(f, ducked[name] or m, root)
		local listener: AudioListener? = nil
		if gb.spatial then
			local l = Instance.new("AudioListener")
			l.Name = "Listener_" .. name
			l.AudioInteractionGroup = "kit_" .. name
			if gb.acoustic then
				acousticOn = try(l, "AcousticSimulationEnabled", true) or acousticOn
			end
			l.Parent = Workspace.CurrentCamera
			if gb.reverb then
				-- the zone's reverb sits between the ears and the fader; Bypass = dry (Sfx.reverb sets it)
				local rv = Instance.new("AudioReverb")
				rv.Name = "Reverb_" .. name
				rv.Bypass = true
				rv.Parent = root
				wire(l, rv, root)
				wire(rv, f, root)
				reverbs[name] = rv
			else
				wire(l, f, root)
			end
			listener = l
		end
		buses[name] = { fader = f, listener = listener, base = gb.volume }
	end
	-- the sidechain keys: the keying bus's fader also feeds the compressor's Sidechain pin (the music dips under it)
	for _, d in plan.ducks do
		for _, key in d.keys do
			local b = buses[key]
			if b then
				wire(b.fader, ducked[d.bus], root, "Sidechain")
			end
		end
	end
	root.Parent = Players.LocalPlayer
	graphRoot = root
	master = m
	-- the camera is replaced on respawn: move the listeners to the new one
	Workspace:GetPropertyChangedSignal("CurrentCamera"):Connect(function()
		for _, b in buses do
			if b.listener then
				b.listener.Parent = Workspace.CurrentCamera
			end
		end
	end)
end

local function stopVoice(v: SfxRules.Voice)
	local p = players[v.id]
	if p then
		p:Stop()
		local holder = p:FindFirstAncestorOfClass("Attachment")
		if holder and holder.Name == "KitSfxAt" then
			holder:Destroy()
		else
			p:Destroy()
		end
		players[v.id] = nil
	end
	for i, a in active do
		if a.id == v.id then
			table.remove(active, i)
			break
		end
	end
end

local function duck(spec: any)
	if type(spec) ~= "table" or type(spec.bus) ~= "string" then
		return
	end
	local b = buses[spec.bus]
	if not b then
		return
	end
	local to = math.clamp(tonumber(spec.to) or 0.5, 0, 1) * b.base
	local seconds = math.clamp(tonumber(spec.seconds) or 0.35, 0.05, 5)
	TweenService:Create(b.fader, TweenInfo.new(0.04), { Volume = to }):Play()
	task.delay(seconds, function()
		TweenService:Create(b.fader, TweenInfo.new(0.35), { Volume = b.base }):Play()
	end)
end

local function playHere(event: string, params: { [string]: any }?)
	buildGraph()
	local p: { [string]: any } = table.clone(params or {})
	-- where it is heard from: the distance to the camera (the far layer, priority, air absorption) and whether it is
	-- the local player's own (their character made it: it outranks the crowd)
	local at0 = p.at
	local pos: Vector3? = if typeof(at0) == "Vector3"
		then at0 :: Vector3
		elseif typeof(at0) == "Instance" and (at0 :: Instance):IsA("BasePart") then (at0 :: BasePart).Position
		elseif typeof(at0) == "Instance" and (at0 :: Instance):IsA("Attachment") then (at0 :: Attachment).WorldPosition
		else nil
	local cam = Workspace.CurrentCamera
	if pos and cam and p.distance == nil then
		p.distance = (pos - cam.CFrame.Position).Magnitude
	end
	local me = Players.LocalPlayer and Players.LocalPlayer.Character
	local mine = p.mine == true or (me ~= nil and typeof(at0) == "Instance" and (at0 :: Instance):IsDescendantOf(me))
	local r, why = SfxRules.resolve(catalog, event, p, rng:NextNumber(), rng:NextNumber())
	if not r then
		warnOnce(event, why or event)
		return
	end
	local cutoff
	r.priority, cutoff = SfxRules.listen(r, p.distance, mine)
	-- (the game's one clock, as kit.Moves times every hit: LIMITATIONS_FIXES_V4 13.1)
	local now = Workspace:GetServerTimeNow()
	local ok, steal = SfxRules.admit(r, active, now, lastStart, tonumber(catalog.maxVoices) or 32)
	if not ok then
		dropped += 1
		return
	end
	if steal then
		stopVoice(steal)
	end
	local id = takeId(r.sound)
	if not id then
		return
	end
	local bus = buses[r.bus] or buses.sfx
	local player = Instance.new("AudioPlayer")
	player.Asset = id
	player.Volume = r.volume
	player.PlaybackSpeed = r.pitch
	local at = p.at
	local holder: Instance
	if SPATIAL[r.bus] and (typeof(at) == "Vector3" or typeof(at) == "Instance") then
		local emitter = Instance.new("AudioEmitter")
		emitter.AudioInteractionGroup = "kit_" .. (if buses[r.bus] then r.bus else "sfx")
		emitter:SetDistanceAttenuation({ [0] = 1, [r.rolloff[1]] = 1, [r.rolloff[2]] = 0 })
		if acousticOn then
			try(emitter, "AcousticSimulationEnabled", true) -- walls muffle it, corners bend it (SoundService's switch: kit Acoustics)
		end
		-- DIRECTIVITY: a barrel / blade / mouth radiates along its holder's LookVector (a bare point has no facing)
		if r.directivity and typeof(at) == "Instance" then
			pcall(function()
				emitter:SetAngleAttenuation(r.directivity :: any)
			end)
		end
		if typeof(at) == "Vector3" then
			local att = Instance.new("Attachment")
			att.Name = "KitSfxAt"
			att.WorldPosition = at
			att.Parent = Workspace.Terrain
			holder = att
		else
			holder = at :: Instance
		end
		emitter.Parent = holder
		player.Parent = if typeof(at) == "Vector3" then holder else emitter
		-- the air between: a low-pass at the distance's cutoff (no filter when it is near: nothing to take)
		if cutoff < 18000 then
			local filter = Instance.new("AudioFilter")
			pcall(function()
				local f: any = filter
				f.FilterType = (Enum :: any).AudioFilterType.Lowpass12dB
				f.Frequency = cutoff
			end)
			filter.Parent = player
			wire(player, filter, player)
			wire(filter, emitter, player)
		else
			wire(player, emitter, player)
		end
	else
		player.Parent = bus.fader
		wire(player, bus.fader, player)
	end
	nextId += 1
	local voice = { event = r.event, priority = r.priority, started = now, id = nextId }
	table.insert(active, voice)
	players[voice.id] = player
	lastStart[r.event] = now
	player.Ended:Once(function()
		stopVoice(voice)
	end)
	-- an asset that never loads must not hold a voice forever
	task.delay(30, function()
		if players[voice.id] == player then
			stopVoice(voice)
		end
	end)
	player:Play()
	if r.duck then
		duck(r.duck)
	end
end

-- ---------------------------------------------------------------- server -> clients
local remote: RemoteEvent? = nil
local function getRemote(): RemoteEvent?
	if remote then
		return remote
	end
	if RunService:IsServer() then
		local r = ReplicatedStorage:FindFirstChild(REMOTE_NAME)
		if not r then
			r = Instance.new("RemoteEvent")
			r.Name = REMOTE_NAME
			r.Parent = ReplicatedStorage
		end
		remote = r :: RemoteEvent
	else
		remote = ReplicatedStorage:WaitForChild(REMOTE_NAME, 10) :: RemoteEvent?
	end
	return remote
end

function Sfx.broadcast(event: string, at: (Vector3 | Instance)?, params: { [string]: any }?, except: Player?)
	assert(RunService:IsServer(), "Sfx.broadcast is server-only (clients: Sfx.play)")
	local r = getRemote()
	if not r then
		return
	end
	local p = table.clone(params or {})
	p.at = at
	for _, plr in Players:GetPlayers() do
		if plr ~= except then
			r:FireClient(plr, event, p)
		end
	end
end

function Sfx.play(event: string, params: { [string]: any }?)
	if RunService:IsServer() then
		local p: { [string]: any } = params or {}
		Sfx.broadcast(event, p.at, p)
		return
	end
	playHere(event, params)
end

function Sfx.snapshot(name: string?, seconds: number?)
	if RunService:IsServer() then
		return
	end
	buildGraph()
	local target = SfxRules.snapshot(catalog, name)
	for busName, b in buses do
		b.base = target[busName] or b.base
		TweenService:Create(b.fader, TweenInfo.new(seconds or 0.6), { Volume = b.base }):Play()
	end
end

function Sfx.setBus(name: string, volume: number)
	if RunService:IsServer() then
		return
	end
	buildGraph()
	if name == "master" and master then
		master.Volume = math.clamp(volume, 0, 2)
		return
	end
	local b = buses[name]
	if b then
		b.base = math.clamp(volume, 0, 2)
		b.fader.Volume = b.base
	end
end

-- CLIENT: the zone's reverb on the spatial sfx / voice buses (SfxRules.REVERBS name, a catalog "reverbs" name, or nil =
-- dry). One pooled AudioReverb per bus: entering a zone re-tunes it, leaving bypasses it (EchoZones calls this).
function Sfx.reverb(name: string?)
	if RunService:IsServer() then
		return
	end
	buildGraph()
	local s = if name then SfxRules.reverb(name, catalog) else nil
	reverbName = if s then name else nil
	for _, rv in reverbs do
		if s then
			try(rv, "DecayTime", s.decay)
			try(rv, "EarlyDelayTime", s.early)
			try(rv, "LateDelayTime", s.late)
			try(rv, "Density", s.density)
			try(rv, "Diffusion", s.diffusion)
			try(rv, "WetLevel", s.wet)
			try(rv, "DryLevel", s.dry)
			try(rv, "HighCutFrequency", s.highCut)
			try(rv, "Bypass", false)
		else
			try(rv, "Bypass", true)
		end
	end
end

-- CLIENT: the built graph (for playtests: the graph is held to SfxRules.graph there) -> the KitSfx folder, the zone
-- reverb's name, and whether the engine took acoustic simulation on the listeners
function Sfx.graph(): { root: Folder?, reverb: string?, acoustic: boolean }
	if not RunService:IsServer() then
		buildGraph()
	end
	return { root = graphRoot, reverb = reverbName, acoustic = acousticOn }
end

function Sfx.stats(): { voices: number, byBus: { [string]: number }, dropped: number }
	local byBus: { [string]: number } = {}
	for _, v in active do
		local e = catalog.events and catalog.events[v.event]
		local b = (type(e) == "table" and e.bus) or "sfx"
		byBus[b] = (byBus[b] or 0) + 1
	end
	return { voices = #active, byBus = byBus, dropped = dropped }
end

-- ---------------------------------------------------------------- the kit's other sound modules, on the same graph
-- Sfx.voice(sound, opts?) -> VoiceHandle?   one Audio API voice for the kit's own modules (Music's stems, Ambience's
-- beds and scatter, WindVoice, GustEvents, EchoZones, Foley through Assets.play): an AudioPlayer on a bus of THIS graph
-- (its fader, snapshots, ducking and the master compressor apply), spatial when it has `at` (an AudioEmitter in the
-- bus's interaction group, rolled off from `near` to `range`, acoustic simulation when the graph has it), 2D when not;
-- `eq` = { high, mid, low } dB puts an AudioEqualizer between the player and where it goes (a sound heard through water
-- or stone). PARALLAX_FINAL_CLOSURE_SPEC Step 6 / SFX-X: 0 legacy Sound / SoundGroup / EqualizerSoundEffect left.
--   sound: a logical name (a random take of name, name_2 ... from assets/ids.json) or an asset id ("rbxassetid://...")
--   opts: { bus = "sfx" | "music" | "ambience" | "voice" | "ui", at = Vector3 | Instance, volume, pitch, looped,
--           near, range, eq = { high, mid, low }, timePosition, autoplay = true }
-- SERVER: only with `at` (an emitter every client's listener of that bus hears); a 2D server sound has no Audio API
-- form - it warns once and plays nothing (Sfx.broadcast an event instead).
-- A voice is not counted against an event's voice limits (those are the catalog's events: Sfx.play).
export type VoiceHandle = {
	player: AudioPlayer,
	setVolume: (number) -> (),
	setPitch: (number) -> (),
	play: () -> (),
	stop: () -> (),
	playing: () -> boolean,
}

local function assetOf(sound: string): string?
	if string.find(sound, "^rbxassetid://") or string.find(sound, "^https?://") then
		return sound
	end
	return takeId(sound)
end

function Sfx.voice(sound: string, opts: { [string]: any }?): VoiceHandle?
	local o: { [string]: any } = opts or {}
	local id = assetOf(sound)
	if not id then
		return nil
	end
	local busName: string = if type(o.bus) == "string" then o.bus else "sfx"
	local at = o.at
	local server = RunService:IsServer()
	if server and at == nil then
		warnOnce(
			"voice2d:" .. sound,
			`Sfx.voice("{sound}") on the server without \`at\`: a 2D sound is a client's - Sfx.broadcast an event`
		)
		return nil
	end
	if not server then
		buildGraph()
	end
	local player = Instance.new("AudioPlayer")
	player.Name = "KitVoice_" .. sound
	player.Asset = id
	player.Volume = tonumber(o.volume) or 1
	player.PlaybackSpeed = tonumber(o.pitch) or 1
	player.Looping = o.looped == true
	if tonumber(o.timePosition) then
		player.TimePosition = tonumber(o.timePosition) :: number
	end
	local holder: Instance? = nil -- (an Attachment this voice made, removed with it)
	local madeEmitter: Instance? = nil -- (an emitter this voice put on the caller's own part: removed, the part stays)
	local last: Instance = player -- the node the chain continues from
	local eqNode: Instance? = nil
	if type(o.eq) == "table" then
		local eq = Instance.new("AudioEqualizer")
		try(eq, "HighGain", tonumber(o.eq.high) or 0)
		try(eq, "MidGain", tonumber(o.eq.mid) or 0)
		try(eq, "LowGain", tonumber(o.eq.low) or 0)
		eq.Parent = player
		eqNode = eq
	end
	local spatial = SPATIAL[busName] == true or server
	if spatial and (typeof(at) == "Vector3" or typeof(at) == "Instance") then
		local emitter = Instance.new("AudioEmitter")
		emitter.AudioInteractionGroup = "kit_" .. (if server or buses[busName] then busName else "sfx")
		local near = math.max(0, tonumber(o.near) or 6)
		local range = math.max(near + 1, tonumber(o.range) or 120)
		emitter:SetDistanceAttenuation({ [0] = 1, [near] = 1, [range] = 0 })
		if acousticOn then
			try(emitter, "AcousticSimulationEnabled", true)
		end
		if typeof(at) == "Vector3" then
			local att = Instance.new("Attachment")
			att.Name = "KitSfxAt"
			att.WorldPosition = at
			att.Parent = Workspace.Terrain
			holder = att
			emitter.Parent = att
		else
			emitter.Parent = at :: Instance
			madeEmitter = emitter
		end
		player.Parent = emitter
		if eqNode then
			wire(last, eqNode, player)
			last = eqNode
		end
		wire(last, emitter, player)
	else
		local bus = buses[busName] or buses.sfx
		if not bus then
			player:Destroy()
			return nil
		end
		player.Parent = bus.fader
		if eqNode then
			wire(last, eqNode, player)
			last = eqNode
		end
		wire(last, bus.fader, player)
	end
	local alive = true
	local function stop()
		if not alive then
			return
		end
		alive = false
		pcall(function()
			player:Stop()
		end)
		if holder then
			holder:Destroy()
		elseif madeEmitter then
			madeEmitter:Destroy()
		else
			player:Destroy()
		end
	end
	if not player.Looping then
		player.Ended:Once(stop)
		task.delay(30, stop) -- (an asset that never loads must not hold a voice forever)
	end
	local handle: VoiceHandle = {
		player = player,
		setVolume = function(v: number)
			if alive then
				player.Volume = v
			end
		end,
		setPitch = function(v: number)
			if alive then
				player.PlaybackSpeed = v
			end
		end,
		play = function()
			if alive then
				player:Play()
			end
		end,
		stop = stop,
		playing = function(): boolean
			return alive and player.IsPlaying
		end,
	}
	if o.autoplay ~= false then
		player:Play()
	end
	return handle
end

-- Sfx.preload(events) -> loaded, wanted: every take of every sound the named events can play, fetched before they are
-- needed (ContentProvider:PreloadAsync on AudioPlayers that name them): the first hit of a fight starts on time instead
-- of a frame (or 166 ms) late - kit_integration_arena's A/V check, 2026-11-22. Yields; call it in a task at spawn.
local function soundsOf(spec: any, out: { [string]: boolean })
	if type(spec) ~= "table" then
		return
	end
	if type(spec.sound) == "string" then
		out[spec.sound] = true
	end
	if type(spec.sounds) == "table" then
		for _, s in spec.sounds do
			if type(s) == "string" then
				out[s] = true
			end
		end
	end
	if type(spec.cases) == "table" then
		for _, c in spec.cases do
			soundsOf(c, out)
		end
	end
	soundsOf(spec.far, out)
end

function Sfx.preload(events: { string }): (number, number)
	local names: { [string]: boolean } = {}
	for _, e in events do
		soundsOf(catalog.events and catalog.events[e], names)
	end
	local items: { Instance } = {}
	local sounds = registry.sounds or {}
	for name in names do
		local key, n = name, 1
		while sounds[key] do
			local p = Instance.new("AudioPlayer")
			p.Asset = sounds[key]
			table.insert(items, p)
			n += 1
			key = `{name}_{n}`
		end
	end
	local loaded = 0
	pcall(function()
		game:GetService("ContentProvider"):PreloadAsync(items, function(_, status)
			if status == Enum.AssetFetchStatus.Success then
				loaded += 1
			end
		end)
	end)
	for _, p in items do
		p:Destroy()
	end
	return loaded, #items
end
-- the client half: listen for server broadcasts (the kit's client script requires this module once)
function Sfx.startClient()
	if RunService:IsServer() then
		return
	end
	local r = getRemote()
	if not r then
		warn("[Sfx] no SfxPlay remote (the server never required ReplicatedStorage.kit.Sfx)")
		return
	end
	r.OnClientEvent:Connect(function(event: any, params: any)
		if type(event) == "string" and (params == nil or type(params) == "table") then
			playHere(event, params)
		end
	end)
end

if RunService:IsServer() then
	getRemote() -- the remote exists before any client asks for it
end

return Sfx

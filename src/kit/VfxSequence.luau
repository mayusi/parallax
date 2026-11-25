-- VfxSequence (kit) — V5: a CHOREOGRAPHED MULTI-SHOT sequence played on the client (LIMITATIONS_FIXES_V4 §3.4 step 3,
-- §13.3.3): Charge -> a 1-frame VfxMood beat + a B4 impact plate + a hitstop -> a multi-cut reveal, every beat on
-- the 60 fps clock. The rules (validation, the V5 shape, the timeline, the clock that never fires early and never pops
-- a 1-frame beat before it was drawn) are src/kit/VfxSequenceRules.luau - pure, proven in
-- kit/test/spec/vfxsequence.spec.luau. This file only turns the timeline's events into the engine's things.
--
--   VfxSequence.play(seq, opts) -> handle         seq: a .seq.json table (ReplicatedStorage.VfxPresets.sequences.<n>)
--     opts = {
--       at: CFrame,                              where the hit is (the shots are framed round it; layers play there)
--       victim: Model?,                          who is hit (victim_reaction -> VfxImpact.onVictimHit)
--       shots: { [shot]: (at: CFrame) -> CFrame }?   a game's own camera framings (else DEFAULT_SHOTS)
--       hitstop: ((seconds: number) -> ())?      the GAME's freeze (Moves' hitstop): the sequence only asks for it
--       sfx: ((event: string, at: CFrame) -> ())?, vfx: ((preset: string, at: CFrame) -> ())?
--       plates: { [key]: spec }?, textures: registry?    (else VfxPresets.plates / VfxPresets._textures)
--       handlers: { [kind]: (ev, ctx) -> () }?   replace one event kind's handler (a cutscene's own camera)
--     }
--     handle:stop()  ends it at once: the camera, field of view, mood and plates are given back
-- Client only. The camera goes Scriptable for the sequence's cuts and comes back as it was.
local Rules = require("./VfxSequenceRules")
local VfxPlate = require("./VfxPlate")

local VfxSequence = {}
VfxSequence.Rules = Rules

-- framings round the hit (the hit's CFrame: its LookVector the attacker's facing): distances in studs
local function look(from: Vector3, to: Vector3): CFrame
	return CFrame.lookAt(from, to)
end
VfxSequence.DEFAULT_SHOTS = {
	wide = function(at: CFrame): CFrame
		return look((at * CFrame.new(10, 6, 22)).Position, at.Position)
	end,
	close = function(at: CFrame): CFrame
		return look((at * CFrame.new(2.5, 1.5, 6)).Position, at.Position)
	end,
	low = function(at: CFrame): CFrame
		return look((at * CFrame.new(-4, -2, 9)).Position, at.Position + Vector3.new(0, 2, 0))
	end,
	high = function(at: CFrame): CFrame
		return look((at * CFrame.new(3, 16, 8)).Position, at.Position)
	end,
	over = function(at: CFrame): CFrame
		return look((at * CFrame.new(2, 3, 5)).Position, (at * CFrame.new(0, 1, -10)).Position)
	end,
	side = function(at: CFrame): CFrame
		return look((at * CFrame.new(14, 2, 0)).Position, at.Position)
	end,
	back = function(at: CFrame): CFrame
		return look((at * CFrame.new(0, 3, -12)).Position, at.Position)
	end,
	top = function(at: CFrame): CFrame
		return look(at.Position + Vector3.new(0, 24, 0.01), at.Position)
	end,
}

local presetsFolder: any = nil
local function presets(): any
	if presetsFolder == nil then
		presetsFolder = game:GetService("ReplicatedStorage"):FindFirstChild("VfxPresets") or false
	end
	return presetsFolder or nil
end

local function child(folder: any, name: string): any
	local f = presets()
	local sub = f and f:FindFirstChild(folder)
	local m = sub and sub:FindFirstChild(name)
	return if m and m:IsA("ModuleScript") then (require :: any)(m) else nil
end

function VfxSequence.play(seq: any, opts: any?)
	local o = opts or {}
	local tl = Rules.compile(seq) -- raises (naming every fault) on a sequence that does not validate
	local RunService = game:GetService("RunService")
	local camera = workspace.CurrentCamera
	local at: CFrame = o.at or CFrame.new()
	local clock = Rules.clock()
	local shots = o.shots or VfxSequence.DEFAULT_SHOTS
	local saved = { type = camera.CameraType, cf = camera.CFrame, fov = camera.FieldOfView }
	local cutCF: CFrame? = nil
	local fovs: { [any]: { delta: number, frames: number, from: number } } = {}
	local shakes: { [any]: { amp: number, frames: number, from: number } } = {}
	local plates: { [any]: { handle: any, from: number } } = {}
	local moodIds: { [any]: any } = {}
	local mood = nil
	local frame = 0
	local rng = Random.new()
	local ctx = { at = at, camera = camera, victim = o.victim, timeline = tl }

	local function stageMood(): any
		if mood == nil then
			local ok, VfxStage = pcall(require, script.Parent:FindFirstChild("VfxStage"))
			mood = if ok and VfxStage then VfxStage._mood else false
		end
		return mood or nil
	end

	local H: { [string]: (ev: any) -> () } = {}
	H.camera_cut = function(ev)
		local shot = shots[ev.data.shot] or VfxSequence.DEFAULT_SHOTS[ev.data.shot]
		camera.CameraType = Enum.CameraType.Scriptable
		cutCF = shot(at)
		camera.CFrame = cutCF :: CFrame
	end
	H.fov_punch = function(ev)
		fovs[ev] = { delta = ev.data.delta, frames = ev.data.frames, from = frame }
	end
	H.shake = function(ev)
		shakes[ev] = { amp = ev.data.amp, frames = ev.data.frames, from = frame }
	end
	H.mood_push = function(ev)
		local m = stageMood()
		if m then
			local id = {}
			moodIds[ev.beat] = id
			m:push(id, ev.data.priority or 50, ev.data.values)
		end
	end
	H.mood_push_end = function(ev)
		local m, id = stageMood(), moodIds[ev.beat]
		if m and id then
			m:pop(id)
			moodIds[ev.beat] = nil
		end
	end
	H.impact_plate = function(ev)
		local spec = (o.plates and o.plates[ev.data.plate]) or child("plates", ev.data.plate .. ".plate")
		if not spec then
			warn(`[VfxSequence] no plate "{ev.data.plate}" (kit vfx plate {ev.data.plate} --kind ...)`)
			return
		end
		local textures = o.textures
		if not textures then
			local f = presets()
			local t = f and f:FindFirstChild("_textures")
			textures = if t then (require :: any)(t) else {}
		end
		local s = table.clone(spec)
		s.rate = ev.data.rate or s.rate
		plates[ev.beat] = { handle = VfxPlate.show(s, { textures = textures, mode = "Hold" }), from = frame }
	end
	H.impact_plate_end = function(ev)
		local p = plates[ev.beat]
		if p then
			p.handle:destroy()
			plates[ev.beat] = nil
		end
	end
	H.hitstop = function(ev)
		if o.hitstop then
			o.hitstop(ev.data.frames / Rules.FPS)
		end
	end
	H.vfx_layers = function(ev)
		for _, name in ev.data do
			if o.vfx then
				o.vfx(name, at)
			else
				local ok, Vfx = pcall(require, script.Parent:FindFirstChild("Vfx"))
				if ok and Vfx then
					Vfx.play(name, at)
				end
			end
		end
	end
	H.sfx_event = function(ev)
		if o.sfx then
			o.sfx(ev.data, at)
		end
	end
	H.victim_reaction = function(ev)
		if o.victim then
			local ok, VfxImpact = pcall(require, script.Parent:FindFirstChild("VfxImpact"))
			if ok and VfxImpact and VfxImpact.onVictimHit then
				local n = ev.data.normal
				local normal = if n then Vector3.new(n[1], n[2], n[3]) else at.RightVector
				VfxImpact.onVictimHit(o.victim, at, normal, ev.data.power)
			end
		end
	end
	for kind, fn in o.handlers or {} do
		H[kind] = function(ev)
			fn(ev, ctx)
		end
	end

	local conn: RBXScriptConnection? = nil
	local stopped = false
	local function stop()
		if stopped then
			return
		end
		stopped = true
		if conn then
			conn:Disconnect()
		end
		for _, p in plates do
			p.handle:destroy()
		end
		local m = stageMood()
		for _, id in moodIds do
			if m then
				m:pop(id)
			end
		end
		camera.FieldOfView = saved.fov
		if cutCF then
			camera.CFrame = saved.cf
			camera.CameraType = saved.type
		end
	end

	conn = RunService.RenderStepped:Connect(function(dt: number)
		for _, ev in Rules.step(tl, clock, dt) do
			local fn = H[ev.kind]
			if fn then
				local ok, err = pcall(function()
					fn(ev)
				end)
				if not ok then
					warn(`[VfxSequence] {seq.name}: {ev.kind} at frame {ev.frame}: {err}`)
				end
			end
		end
		frame = math.max(clock.frame, 0)
		-- what lasts over frames: the field of view punches back, the shake dies down, the plates step their cells
		local fov = 0
		for ev, f in fovs do
			local u = (frame - f.from) / f.frames
			if u >= 1 then
				fovs[ev] = nil
			else
				fov += f.delta * (1 - u) * (1 - u)
			end
		end
		camera.FieldOfView = saved.fov + fov
		local base = cutCF or camera.CFrame
		local amp = 0
		for ev, s in shakes do
			local u = (frame - s.from) / s.frames
			if u >= 1 then
				shakes[ev] = nil
			else
				amp += s.amp * (1 - u)
			end
		end
		if cutCF then
			local r = math.rad(amp)
			camera.CFrame = base * CFrame.Angles(rng:NextNumber(-r, r), rng:NextNumber(-r, r), 0)
		end
		for _, p in plates do
			p.handle:step(frame - p.from)
		end
		if Rules.done(tl, clock) and frame >= tl.frames then
			stop()
		end
	end)
	return { stop = stop, timeline = tl }
end

return VfxSequence

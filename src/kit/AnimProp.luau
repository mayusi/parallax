--!strict
-- AnimProp — A PROP'S CLIP PLAYED IN STEP WITH A CHARACTER'S (LIMITATIONS_FIXES_V3 Stage D: "Attach
-- AnimationController + Animator + Motor6D prop trees, step lockstep with character track TimePosition (GunReload,
-- ChestOpen, Door), emit prop markers once"; card r66z: "the runtime has no prop player").
--
-- A prop's clip (kit/anim/prop_rig.py go -> `lune run kit anim prop <Prop>`: KitAnimations.props.<Prop>.<Clip>) moves
-- the joints of a model the game spawned (src/kit/Models.luau: a Motor6D at every hinge and slide). Nothing played it.
-- This does, on the CHARACTER's clock: a gun's slide racks on the frame the hand pulls it, a chest's lid lifts with
-- the arms that lift it, whatever the character's clip does to its time (a hit-stop, a slow-down, a rewind, a loop).
--
--   local animator = AnimProp.attach(model)                     -- AnimationController + Animator on the model
--   local player = AnimProp.play(model, "Chest/ChestOpen", characterTrack, {
--       offset = 0.2,                                          -- the prop's clip starts 0.2 s into the character's
--       onMarker = function(event) ... end,                    -- the prop clip's own markers, each once
--   })
--   player.stop()                                               -- (it stops by itself when the character's does)
--
-- THE CLOCK (pure: AnimProp.timeFor): the prop's time is (character time - offset) x rate, held at its first frame
-- before it starts and at its last after it ends; a looped prop clip wraps instead. The prop's track plays at speed
-- 0 and its TimePosition is SET every frame before the engine animates (RunService.PreAnimation): the character's
-- time read there is the previous frame's, so it is led by the frame's own step (dt x the character track's speed),
-- and both land on the same time when the frame is drawn.
-- THE MARKERS (pure: AnimProp.cross): a track whose time is set does not fire its markers (the engine fires them only
-- when its own playback crosses them: src/kit/AnimMarks), so this says them itself, from the prop clip's clock: each
-- marker once when the clock first reaches it; never again in that pass when the time winds back over it (a rewind,
-- a jitter); a looped prop clip's wrap is a new pass (the markers it had not reached first, then the new pass's);
-- an entry past a marker (played late) does not owe it; a cancel (the character's clip stopped early) ends them; a
-- clip that ran to its end says its last ones.
-- NOT HERE: which prop a character holds (a game's call), the prop's own physics, a prop clip uploaded without its
-- KeyframeSequence (pass its markers as opts.events: an uploaded Animation does not list them).

local AnimProp = {}

export type Link = {
	offset: number?, -- character seconds at which the prop's clip starts (default 0)
	rate: number?, -- prop seconds per character second (default 1)
	length: number, -- the prop clip's length, seconds
	loop: boolean?, -- the prop's clip wraps (a wheel that keeps turning); otherwise it holds its ends
}
export type Event = { name: string, t: number, value: string? }
export type Marks = {
	events: { Event }, -- in time order
	taken: { [number]: boolean },
	from: number, -- where this pass was entered: events before it are not owed
	last: number?,
	cycle: number?, -- a looped prop clip's count of whole cycles at the last step
	pass: number,
	cancelled: boolean,
}

AnimProp.EPS = 1e-4 -- seconds: a marker exactly at the clock is reached

-- the prop's time for a character time, and - a looped prop clip - how many whole cycles it has run (its wraps)
function AnimProp.timeFor(characterTime: number, link: Link): (number, number)
	local length = math.max(link.length, 0)
	local t = (characterTime - (link.offset or 0)) * (link.rate or 1)
	if t ~= t then
		return 0, 0
	end
	if link.loop and length > 0 then
		return t % length, math.floor(t / length) -- (a negative time wraps too: a looped prop is always in its cycle)
	end
	return math.clamp(t, 0, length), 0
end

-- the prop clip's markers, a new record of which were said (a pass entered at `from`, default 0)
function AnimProp.marks(events: { Event }?, from: number?): Marks
	local list: { Event } = table.clone(events or {})
	table.sort(list, function(a: Event, b: Event)
		return a.t < b.t
	end)
	return { events = list, taken = {}, from = from or 0, last = nil, cycle = nil, pass = 1, cancelled = false }
end

-- a new pass: everything may be said once more (the character's clip played again)
function AnimProp.pass(m: Marks, from: number?)
	table.clear(m.taken)
	m.pass += 1
	m.from = from or 0
	m.last = nil
	m.cycle = nil
	m.cancelled = false
end

-- the character's clip stopped early: nothing more is said until a new pass
function AnimProp.cancel(m: Marks)
	m.cancelled = true
end

local function sayUpTo(m: Marks, upTo: number, out: { Event })
	for i, e in m.events do
		if not m.taken[i] and e.t <= upTo + AnimProp.EPS and e.t >= m.from - AnimProp.EPS then
			m.taken[i] = true
			table.insert(out, e)
		end
	end
end

-- THE CLOCK MOVED to `now` (prop seconds): the markers to say, in order. length / looped: the prop clip's; cycle:
-- its count of whole cycles (AnimProp.timeFor's second value) - a wrap is a cycle more, whatever the step; without
-- it a looped clock that went back more than half the clip is taken for a wrap
function AnimProp.cross(m: Marks, now: number, length: number, looped: boolean?, cycle: number?): { Event }
	local out = {}
	if m.cancelled or now ~= now then
		return out
	end
	local last = m.last
	local wrapped = false
	if looped and length > 0 then
		if cycle ~= nil then
			wrapped = m.cycle ~= nil and cycle > (m.cycle :: number)
		else
			wrapped = last ~= nil and now < last - length / 2
		end
	end
	if wrapped then
		sayUpTo(m, length, out) -- the end of the pass that wrapped, then the new pass from its start
		AnimProp.pass(m, 0)
	end
	if cycle ~= nil then
		m.cycle = cycle
	end
	sayUpTo(m, now, out)
	m.last = now
	return out
end

-- the clip RAN TO ITS END: the markers it had not said yet (one at its very end the last step did not reach)
function AnimProp.finish(m: Marks, length: number): { Event }
	local out = {}
	if not m.cancelled then
		sayUpTo(m, length, out)
	end
	m.cancelled = true
	return out
end

-- a KeyframeSequence's markers: each KeyframeMarker under a Keyframe, at that Keyframe's time
function AnimProp.markersOf(sequence: Instance): { Event }
	local out = {}
	for _, kf in sequence:GetChildren() do
		if kf:IsA("Keyframe") then
			for _, mk in kf:GetChildren() do
				if mk:IsA("KeyframeMarker") then
					table.insert(out, { name = mk.Name, t = kf.Time, value = mk.Value })
				end
			end
		end
	end
	table.sort(out, function(a, b)
		return a.t < b.t
	end)
	return out
end

local function lengthOf(sequence: Instance): number
	local length = 0
	for _, kf in sequence:GetChildren() do
		if kf:IsA("Keyframe") then
			length = math.max(length, kf.Time)
		end
	end
	return length
end

-- THE MODEL'S ANIMATOR: an AnimationController + Animator on the spawned model (made once, found after)
function AnimProp.attach(model: Instance): Animator
	local ctrl = model:FindFirstChildOfClass("AnimationController") :: AnimationController?
	if not ctrl then
		local made = Instance.new("AnimationController")
		made.Name = "AnimationController"
		made.Parent = model
		ctrl = made
	end
	local animator = (ctrl :: AnimationController):FindFirstChildOfClass("Animator") :: Animator?
	if not animator then
		local made = Instance.new("Animator")
		made.Parent = ctrl
		animator = made
	end
	return animator :: Animator
end

-- AN OBJECT ON A JOINT OF ITS OWN (kit/anim/handoff.py: a clip's `props` - a magazine handed from the receiver to the
-- hand and back): the Motor6D the character's clip keys, named as the object, Part0 = the carrier part, C0 = the
-- record's c0 (a CFrame), C1 = identity (the object's own origin). Made once, found after; the object is unanchored
-- and welded to nothing else (the joint carries it)
function AnimProp.socket(character: Instance, carrier: string, object: BasePart, c0: CFrame?): Motor6D?
	local part = character:FindFirstChild(carrier)
	if not part or not part:IsA("BasePart") then
		return nil
	end
	local motor = part:FindFirstChild(object.Name) :: Motor6D?
	if not motor or not motor:IsA("Motor6D") then
		local made = Instance.new("Motor6D")
		made.Name = object.Name
		made.Parent = part
		motor = made
	end
	local m = motor :: Motor6D
	m.Part0 = part
	m.Part1 = object
	m.C0 = c0 or CFrame.identity
	m.C1 = CFrame.identity
	object.Anchored = false
	object.Massless = true
	object.CanCollide = false
	if object.Parent ~= character then
		object.Parent = character
	end
	return m
end

-- a prop clip: a KeyframeSequence, an Animation, an asset id, or "<Prop>/<Clip>" (KitAnimations.props) -> (the
-- Animation to load, its sequence when there is one)
local function resolve(clip: Instance | string): (Animation?, Instance?, string?)
	local seq: Instance? = nil
	if typeof(clip) == "Instance" then
		if clip:IsA("Animation") then
			return clip, nil, nil
		end
		seq = clip
	elseif type(clip) == "string" and string.find(clip, "^rbxassetid://") then
		local a = Instance.new("Animation")
		a.AnimationId = clip
		return a, nil, nil
	elseif type(clip) == "string" then
		local prop, name = string.match(clip, "^([%w_]+)/([%w_]+)$")
		local folder = game:GetService("ReplicatedStorage"):FindFirstChild("KitAnimations")
		local props = folder and folder:FindFirstChild("props")
		local own = props and prop and props:FindFirstChild(prop)
		seq = own and name and own:FindFirstChild(name) or nil
		if not seq then
			return nil, nil, `no prop clip "{clip}" (KitAnimations.props.<Prop>.<Clip>: lune run kit anim prop <Prop>)`
		end
	end
	if not seq or not seq:IsA("KeyframeSequence") then
		return nil, nil, 'a prop clip is a KeyframeSequence, an Animation, an asset id or "<Prop>/<Clip>"'
	end
	if not game:GetService("RunService"):IsStudio() then
		return nil, seq, "a KeyframeSequence plays only in Studio: upload it and pass its asset id"
	end
	local ok, id = pcall(function()
		return game:GetService("KeyframeSequenceProvider"):RegisterKeyframeSequence(seq :: KeyframeSequence)
	end)
	if not ok then
		return nil, seq, `the prop clip could not be registered in Studio: {id}`
	end
	local a = Instance.new("Animation")
	a.Name = seq.Name
	a.AnimationId = id
	return a, seq, nil
end

export type Options = {
	offset: number?,
	rate: number?,
	loop: boolean?, -- (default: the sequence's own Loop)
	events: { Event }?, -- the prop clip's markers when it is not a KeyframeSequence here
	onMarker: ((Event) -> ())?,
	hold: boolean?, -- when the character's clip stops, the prop keeps its pose (default: it stops too)
	fadeOut: number?,
	length: number?, -- the prop clip's length when it is an uploaded id (else read off the track once it loads)
}
export type Player = {
	track: AnimationTrack,
	link: Link,
	marks: Marks,
	stop: () -> (),
	-- the last frame's reading (for a probe): the character's time used, the prop's time set
	lastCharacter: number,
	lastProp: number,
}

-- the player driving each model now: a second play on a model stops the first (and a held pose) first
local playing: { [Instance]: Player } = setmetatable({}, { __mode = "k" }) :: any

-- PLAY a prop's clip on the character track's clock -> the player, or nil and why. The character's track must be
-- playing already (a prop started before it would be stopped by its first frame)
function AnimProp.play(
	model: Instance,
	clip: Instance | string,
	characterTrack: AnimationTrack,
	opts: Options?
): (Player?, string?)
	local o: Options = opts or {}
	if not characterTrack.IsPlaying then
		return nil, "the character's track is not playing: Play it first, then the prop on its clock"
	end
	local animation, seq, why = resolve(clip)
	if not animation then
		return nil, why
	end
	local before = playing[model]
	if before then
		before.stop()
		before.track:Stop(0) -- (a held pose too: two prop tracks would blend half and half)
		before.track:Destroy()
	end
	local track = AnimProp.attach(model):LoadAnimation(animation)
	-- an uploaded clip's length is 0 until the asset loads: read it again each frame until it is known
	local length = if seq then lengthOf(seq) else (o.length or track.Length)
	local loop = if o.loop ~= nil then o.loop elseif seq then (seq :: KeyframeSequence).Loop else false
	local link: Link = { offset = o.offset, rate = o.rate, length = length, loop = loop }
	track.Looped = false -- (the clock wraps it, not the engine)
	track.Priority = Enum.AnimationPriority.Action
	local start, startCycle = AnimProp.timeFor(characterTrack.TimePosition, link)
	local marks = AnimProp.marks(o.events or (if seq then AnimProp.markersOf(seq) else {}), start)
	local RunService = game:GetService("RunService")
	local conns: { RBXScriptConnection } = {}
	local player: Player
	local done = false
	local function say(list: { Event })
		if o.onMarker then
			for _, e in list do
				task.spawn(o.onMarker :: any, e)
			end
		end
	end
	local function stop()
		if done then
			return
		end
		done = true
		for _, c in conns do
			c:Disconnect()
		end
		if not o.hold then
			track:Stop(o.fadeOut or 0)
			task.delay((o.fadeOut or 0) + 0.1, function()
				track:Destroy()
			end)
		end
		if playing[model] == player and not o.hold then
			playing[model] = nil
		end
	end
	local function ended()
		-- ran to its end (the character's clip reached its own end): the markers it had not said; else cancelled
		local len = characterTrack.Length
		local ranOut = not characterTrack.Looped and len > 0 and player.lastCharacter >= len - 2 / 60
		if ranOut and not link.loop then
			say(AnimProp.finish(marks, (AnimProp.timeFor(len, link))))
		else
			AnimProp.cancel(marks)
		end
		stop()
	end
	player = {
		track = track,
		link = link,
		marks = marks,
		stop = stop,
		lastCharacter = characterTrack.TimePosition,
		lastProp = start,
	}
	playing[model] = player
	track:Play(0, 1, 0)
	track.TimePosition = start
	if length > 0 then
		say(AnimProp.cross(marks, start, length, loop, startCycle))
	end
	local wrapped = false -- (the character's clip looped: its own signal, not a guess from its time)
	table.insert(
		conns,
		characterTrack.DidLoop:Connect(function()
			wrapped = true
		end)
	)
	local event = (RunService :: any).PreAnimation or RunService.Stepped
	table.insert(
		conns,
		event:Connect(function(a: number, b: number?)
			local dt = if b ~= nil then b else a -- (Stepped passes the time, then the step)
			if not characterTrack.IsPlaying then
				ended()
				return
			end
			local ct = characterTrack.TimePosition + dt * characterTrack.Speed
			local len = characterTrack.Length
			if len > 0 then
				ct = if characterTrack.Looped then ct % len else math.min(ct, len)
			end
			if link.length <= 0 then
				link.length = track.Length -- (an uploaded clip, loaded now or not yet: held at 0 until it is)
				length = link.length
			end
			if wrapped then
				-- the CHARACTER's clip wrapped: a held prop clip says what its end still owed; then a new pass
				-- (a looped prop's clock is in mid-cycle at the wrap: nothing is owed by its end)
				wrapped = false
				if not loop and length > 0 then
					say(AnimProp.cross(marks, (AnimProp.timeFor(len, link)), length, false))
				end
				AnimProp.pass(marks, 0)
			end
			local t, cycle = AnimProp.timeFor(ct, link)
			track.TimePosition = t
			player.lastCharacter, player.lastProp = ct, t
			if length > 0 then
				say(AnimProp.cross(marks, t, length, loop, cycle))
			end
		end)
	)
	table.insert(conns, characterTrack.Stopped:Connect(ended))
	table.insert(
		conns,
		model.AncestryChanged:Connect(function()
			if not model:IsDescendantOf(game) then
				AnimProp.cancel(marks)
				stop()
			end
		end)
	)
	return player, nil
end

return AnimProp

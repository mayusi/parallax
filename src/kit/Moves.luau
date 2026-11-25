--!strict
-- Moves (ReplicatedStorage.kit.Moves) — runs MOVES AS DATA (ReplicatedStorage.KitMoves.<Set> = src/moves, written by
-- `lune run kit move` from assets/moves) with the SERVER as the authority. Rules: MovesRules (pure, tested).
--   SERVER  local fists = Moves.serve("BgFists")          remotes + per-player state + the hit loop
--           fists.use(character, "BgM1_1")                 NPCs / dummies use moves the same way
--           Moves.debug(true)                              draw live hitboxes (the feel lab)
--           fists.hits:Connect(function(c) end)            every contact: { attacker, victim, kind, damage, move, at }
--           Moves.get("BgFists")                           the served handle, for NPCs and playtests
--   CLIENT  local fists = Moves.client("BgFists")
--           fists.use("BgM1_1") · fists.block(true|false) · fists.parry()      (the client only ASKS)
-- The server decides: is the character free (not stunned, not mid-move unless the move's cancel window allows
-- it), which combo step this is, where the hitbox is on THIS frame (GetPartBoundsInBox on the server's own
-- character positions), hit / blocked / chip / parried / dodged (MovesRules.resolve), damage, stun, knockback
-- (a short LinearVelocity, which the owning client simulates), hit-stop (both tracks paused), and the presentation
-- (Sfx / Vfx broadcasts, from the move's data). Clients send only a move NAME and block / parry presses —
-- rate-limited and Guard-checked.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local AnimLayers = require("./AnimLayers")
local Guard = require("./Guard")
local MovesRules = require("./MovesRules")
local RateLimit = require("./RateLimit")

local Moves = {}

local COMBO_GAP = 0.9 -- seconds after a move ends in which the next combo step still counts as the combo
local BUFFER = 0.18 -- seconds: a press this early before the cancel window / the end is held (set.buffer overrides)
local BUFFER_STALE = 0.8 -- wall seconds: a buffered press older than this (hit-stops + a stun in between) is dropped
local PARRY_COVER_MAX = 1.6 -- seconds: the most a parry's riposte can extend the attacker's stun (a late riposte at 1.0 s + hit-stop + 0.3 fits)
local debugOn = false

-- the GAME clock every combat time lives on (started, lastEnded, lastUsed, stunnedUntil, hitstopUntil, parryAt, a
-- buffered press's `made`, a contact's `at`, the victim's KitStunnedUntil attribute): the server's synced timeline,
-- the same number a client reads. Never os.clock (THIS machine's uptime): a time stored on one clock and compared on
-- the other is ~1.79e9 s off (`os.clock() < stunnedUntil` held forever). Only the RateLimit buckets stay on os.clock
-- (local and monotonic). The hit-stop freeze is the move's own clock (moveTime), not this one.
local function gameNow(): number
	return Workspace:GetServerTimeNow()
end

local function loadSet(setName: string): any
	local folder = ReplicatedStorage:WaitForChild("KitMoves", 10)
	local m = folder and folder:FindFirstChild(setName)
	if not m or not m:IsA("ModuleScript") then
		error(`[Moves] no moveset "{setName}" in ReplicatedStorage.KitMoves (run: lune run kit move)`)
	end
	return (require :: any)(m)
end

-- optional presentation modules (a game without Sfx / Vfx / Anim data still fights)
local function optional(name: string): any?
	local ok, mod = pcall(function()
		return (require :: any)(script.Parent:FindFirstChild(name))
	end)
	return if ok then mod else nil
end

local function remotes(setName: string): (RemoteEvent, RemoteEvent)
	local folderName = "KitMoves_" .. setName
	if RunService:IsServer() then
		local f = ReplicatedStorage:FindFirstChild(folderName)
		if not f then
			f = Instance.new("Folder")
			f.Name = folderName
			f.Parent = ReplicatedStorage
		end
		local function ev(n: string): RemoteEvent
			local r = (f :: Instance):FindFirstChild(n)
			if r and r:IsA("RemoteEvent") then
				return r
			end
			local created = Instance.new("RemoteEvent")
			created.Name = n
			created.Parent = f
			return created
		end
		return ev("Use"), ev("Defend")
	end
	local f = ReplicatedStorage:WaitForChild(folderName)
	return f:WaitForChild("Use") :: RemoteEvent, f:WaitForChild("Defend") :: RemoteEvent
end

type State = {
	move: any?,
	moveName: string?,
	started: number,
	track: AnimationTrack?,
	comboIndex: number,
	lastName: string?,
	lastEnded: number,
	hit: { [Model]: boolean },
	blocking: boolean,
	parryAt: number?,
	stunnedUntil: number,
	hitstopUntil: number,
	pausedFor: number, -- seconds of hit-stop already spent inside this move (the move's clock stops too)
	lastUsed: { [string]: number }, -- per move, for cooldowns
	buffered: { name: string, moveAt: number, made: number }?, -- a buffered press: fired when the move's clock reaches moveAt
	checkedFrame: number?, -- the last frame of this move the hit loop has checked (a late step checks every frame passed)
}

-- seconds into the current move on its OWN clock: hit-stop freezes it (pausedFor already holds the whole freeze,
-- so while frozen the remaining part is given back — the clock reads the moment it froze)
local function moveTime(s: State, now: number): number
	return now - s.started - s.pausedFor + math.max(0, s.hitstopUntil - now)
end

-- ---------------------------------------------------------------- server
local served: { [string]: any } = {}

function Moves.serve(setName: string)
	assert(RunService:IsServer(), "Moves.serve is server-only")
	local set = loadSet(setName)
	local names = {}
	for n in set.moves do
		table.insert(names, n)
	end
	local useRemote, defendRemote = remotes(setName)
	local Anim = optional("Anim")
	local Sfx = optional("Sfx")
	local Vfx = optional("Vfx")
	local Bus = optional("Bus") -- the presentation event bus: Hit / Blocked / Chip / Parried / Death for anyone listening
	local states: { [Model]: State } = {}
	local useLimit = RateLimit.new(8, 12)
	local defendLimit = RateLimit.new(8, 12)
	-- the presentation / gameplay bus: every resolved contact, for score, damage numbers, UI, feel probes
	-- ({ attacker, victim, kind = "hit" | "blocked" | "chip" | "parried", damage, move, at = gameNow() })
	local hitEvent = Instance.new("BindableEvent")

	local function stateOf(character: Model): State
		local s = states[character]
		if not s then
			s = {
				started = 0,
				comboIndex = 0,
				lastEnded = -math.huge,
				hit = {},
				blocking = false,
				stunnedUntil = 0,
				hitstopUntil = 0,
				pausedFor = 0,
				lastUsed = {},
			}
			states[character] = s
			character.Destroying:Once(function()
				states[character] = nil
			end)
		end
		return s :: State
	end

	local function rootOf(character: Model): BasePart?
		local r = character:FindFirstChild("HumanoidRootPart")
		return if r and r:IsA("BasePart") then r else nil
	end

	-- INPUT BUFFER (AAA gaps v2 C1): a press a hair before the cancel window / the end is held - on the MOVE's clock
	-- (moveTime freezes in hit-stop, so a hit landing during the wait moves the fire time with it) - and fired then
	local function buffer(s: State, name: string, now: number)
		if not s.move then
			return
		end
		local t = moveTime(s, now)
		local wait = MovesRules.waitFor(s.move, t, name)
		if wait <= (tonumber(set.buffer) or BUFFER) then
			s.buffered = { name = name, moveAt = t + wait, made = now }
		end
	end

	local function use(character: Model, name: string): boolean
		local move = set.moves[name]
		local hum = character:FindFirstChildOfClass("Humanoid")
		if not move or not hum or hum.Health <= 0 then
			return false
		end
		local s = stateOf(character)
		local now = gameNow()
		if now < s.stunnedUntil then
			return false
		end
		if now < s.hitstopUntil then
			-- (in hit-stop the character is frozen: a new move would read the frozen clock ahead) - but a press ON the
			-- contact is the most common combo press, so it is buffered, not eaten (review 2026-10-22)
			buffer(s, name, now)
			return false
		end
		-- the SERVER decides: busy / cancel window, combo order (no opening with the finisher), cooldowns
		local ok, why, comboIndex = MovesRules.allowed(set, {
			moveName = if s.move then s.moveName else nil,
			moveT = if s.move then moveTime(s, now) else nil,
			lastName = s.lastName,
			lastEnded = s.lastEnded,
			comboIndex = s.comboIndex,
			lastUsed = s.lastUsed,
		}, name, now, COMBO_GAP)
		if not ok then
			-- INPUT BUFFER (AAA gaps v2 C1): a press a hair before the cancel window / the end is held and fired then
			if why == "busy" then
				buffer(s, name, now)
			elseif why == "gap" and not s.move then
				-- (the press came on the frame the last move ended: MovesRules.MIN_GAP holds it to the next frame -
				-- buffered, never eaten; the hit loop fires it on its next step)
				s.buffered = { name = name, moveAt = 0, made = now }
			end
			return false
		end
		s.buffered = nil
		s.comboIndex = comboIndex
		s.lastUsed[name] = now
		if s.track then
			s.track:Stop(0.05)
		end
		s.move, s.moveName, s.started, s.hit, s.pausedFor = move, name, now, {}, 0
		s.checkedFrame = -1
		s.blocking = false
		-- MOTION WARPING (AAA gaps v2 C5): the nearest enemy ahead within `warp.range` becomes the move's target - the
		-- client that owns the body reads it off a KitWarpTarget ObjectValue and bends the root travel toward it
		local target: BasePart? = nil
		local attackRoot = rootOf(character)
		if type(move.warp) == "table" and attackRoot then
			local best = math.huge
			local range = tonumber(move.warp.range) or 18
			local cone = math.cos(math.rad(tonumber(move.warp.cone) or 70))
			for other in states do
				local orRoot = if other ~= character then rootOf(other) else nil
				local oh = other:FindFirstChildOfClass("Humanoid")
				if orRoot and oh and oh.Health > 0 then
					local d = orRoot.Position - attackRoot.Position
					local flat = Vector3.new(d.X, 0, d.Z)
					local dist = flat.Magnitude
					if
						dist < range
						and dist > 1e-3
						and attackRoot.CFrame.LookVector:Dot(flat.Unit) >= cone
						and dist < best
					then
						best, target = dist, orRoot
					end
				end
			end
			local old = character:FindFirstChild("KitWarpTarget")
			if old then
				old:Destroy()
			end
			if target then
				local v = Instance.new("ObjectValue")
				v.Name = "KitWarpTarget"
				v.Value = target
				v.Parent = character
				game:GetService("Debris"):AddItem(v, 2)
			end
		end
		-- (made on the move, a move with an upper-body version plays that one: the walk keeps the legs - MovesRules.clipFor)
		local clipName = if Anim and move.anim
			then MovesRules.clipFor(
				move.anim,
				Anim.meta(),
				-- (R6 only: the version is an R6 clip; an R15 body keeps the move's own R15 clip)
				-- (Anim.going: a body walked by Humanoid:MoveTo - an NPC - has MoveDirection at zero and is on the move)
				hum.RigType == Enum.HumanoidRigType.R6 and Anim.going(hum).Magnitude > MovesRules.MOVING
			)
			else nil
		s.track = if Anim and clipName
			then Anim.play(hum, clipName, nil, nil, nil, { inertial = move.inertial, target = target })
			else nil
		-- TRACKING + COMMITMENT (AAA gaps v2 C6): with `track`, the body stops turning for the active frames (turning
		-- is free in startup) and is given back in recovery
		if type(move.track) == "table" and move.frames then
			local fps = move.frames.fps or 60
			local a0 = (move.frames.startup or 0) / fps
			local a1 = a0 + (move.frames.active or 0) / fps
			local was = hum.AutoRotate
			task.delay(a0, function()
				if s.moveName == name and AnimLayers.turnAllowed("active", move.track) == 0 then
					hum.AutoRotate = false
				end
			end)
			task.delay(a1, function()
				-- (only the move that took it gives it back: a move begun in another's active frames read "off" as
				-- the body's own setting and left it off for good)
				if s.moveName == name then
					hum.AutoRotate = was
				end
			end)
		end
		for _, cue in move.sfx or {} do
			if Sfx and type(cue.event) == "string" then
				task.delay(math.max(0, (cue.frame or 0) / (move.frames.fps or 60)), function()
					local root = rootOf(character)
					if root and s.moveName == name then
						Sfx.broadcast(cue.event, root.Position, { weight = cue.weight })
					end
				end)
			end
		end
		for _, cue in move.vfx or {} do
			if Vfx and type(cue.preset) == "string" then
				task.delay(math.max(0, (cue.frame or 0) / (move.frames.fps or 60)), function()
					local root = rootOf(character)
					if root and s.moveName == name then
						Vfx.broadcast(cue.preset, root.CFrame)
					end
				end)
			end
		end
		return true
	end

	local function knockback(target: Model, from: BasePart, kb: { number })
		local root = rootOf(target)
		if not root or (kb[1] == 0 and kb[2] == 0 and kb[3] == 0) then
			return
		end
		-- knockback in the ATTACKER's frame: x = right, y = up, z = forward
		local v = from.CFrame.RightVector * kb[1] + Vector3.yAxis * kb[2] + from.CFrame.LookVector * kb[3]
		local att = Instance.new("Attachment")
		att.Parent = root
		local lv = Instance.new("LinearVelocity")
		lv.Attachment0 = att
		lv.VectorVelocity = v
		lv.MaxForce = math.huge
		lv.RelativeTo = Enum.ActuatorRelativeTo.World
		lv.Parent = root
		task.delay(0.12, function()
			lv:Destroy()
			att:Destroy()
		end)
	end

	local function hitstop(s: State, seconds: number)
		if seconds <= 0 then
			return
		end
		-- only the time this hit-stop ADDS beyond one already running: three victims in one frame (or two attackers
		-- hitting one victim) froze 0.06 s but added 0.18 s to the clock — the move replayed its frames
		local now = gameNow()
		local untilT = math.max(s.hitstopUntil, now + seconds)
		s.pausedFor += untilT - math.max(s.hitstopUntil, now)
		s.hitstopUntil = untilT
		local track = s.track
		if track then
			track:AdjustSpeed(0)
			task.delay(seconds, function()
				if gameNow() >= s.hitstopUntil - 1e-3 then
					track:AdjustSpeed(1)
				end
			end)
		end
	end

	-- a clip started AT one of its own markers (a reaction at its Hit, a parry at its Parry): the contact lands on the
	-- frame the hit-stop freezes, so both bodies hold the contact before the recoil
	local function playAtMarker(hum: Humanoid, name: string, marker: string): AnimationTrack?
		if not Anim then
			return nil
		end
		local meta: any = Anim.meta()
		local track = Anim.play(hum, name, 0.02)
		local at = nil
		for _, e in (meta[name] and meta[name].events) or {} do
			if type(e) == "table" and e.name == marker then
				at = e.t
			end
		end
		if track and type(at) == "number" then
			track.TimePosition = math.max(0, at - 1 / 60)
		end
		return track
	end

	local function apply(attacker: Model, s: State, victim: Model)
		local vs = stateOf(victim)
		local vh = victim:FindFirstChildOfClass("Humanoid")
		local aroot = rootOf(attacker)
		if not vh or vh.Health <= 0 or not aroot then
			return
		end
		local now = gameNow()
		local o = MovesRules.resolve(s.move, {
			now = now,
			blocking = vs.blocking,
			-- (a move the defender started at or after its parry closes it: MovesRules.parryAtContact)
			parryAt = MovesRules.parryAtContact(vs.parryAt, if vs.move then vs.started else nil),
			iframes = victim:GetAttribute("KitIFrames") == true,
		}, s.comboIndex)
		local onHit = s.move.onHit or {}
		local pos = (rootOf(victim) or aroot).Position
		if o.kind ~= "dodged" then
			hitEvent:Fire({
				attacker = attacker,
				victim = victim,
				kind = o.kind,
				damage = if o.kind == "parried" then 0 else o.damage,
				move = s.moveName,
				at = now,
			})
			if Bus then
				-- (the event's name from its kind: hit -> Hit, blocked -> Blocked, chip -> Chip, parried -> Parried)
				Bus.publish(string.upper(string.sub(o.kind, 1, 1)) .. string.sub(o.kind, 2), {
					attacker = attacker,
					victim = victim,
					damage = if o.kind == "parried" then 0 else o.damage,
					move = s.moveName,
					at = pos,
					weight = onHit.weight,
					surface = victim:GetAttribute("KitSurface") or "flesh",
				}, { near = 250 })
			end
		end
		if o.kind == "parried" then
			s.stunnedUntil = now + o.attackerStun
			if s.track then
				s.track:Stop(0.1)
			end
			s.move, s.moveName = nil, nil
			-- the PARRY on screen (the set's `parry` = { anim, stagger }; KatanaKaeshi, 2026-10-24): the defender's
			-- deflect clip from its Parry marker (the clash on the hit-stop's frame, frozen by the hit-stop below);
			-- the attacker - stunned - takes its stagger when the defender's riposte LANDS (its Hit, after the Parry)
			local pz = (set :: any).parry
			if Anim and type(pz) == "table" then
				local ah = attacker:FindFirstChildOfClass("Humanoid")
				if vh and type(pz.anim) == "string" then
					if vs.track then
						vs.track:Stop(0.02)
					end
					vs.track = playAtMarker(vh, pz.anim, "Parry")
				end
				if ah and type(pz.stagger) == "string" then
					local meta: any = Anim.meta()
					local events = (type(pz.anim) == "string" and meta[pz.anim] and meta[pz.anim].events) or {}
					local tParry, tHit = nil, nil
					for _, e in events do
						if type(e) == "table" and e.name == "Parry" and type(e.t) == "number" then
							tParry = if tParry then math.min(tParry, e.t) else e.t
						end
					end
					for _, e in events do -- the riposte = the first Hit AFTER the Parry (a Hit before it is not one)
						if
							type(e) == "table"
							and e.name == "Hit"
							and type(e.t) == "number"
							and (tParry == nil or e.t > tParry)
						then
							tHit = if tHit then math.min(tHit, e.t) else e.t
						end
					end
					local delay = if type(tParry) == "number" and type(tHit) == "number"
						then math.max(0, tHit - tParry)
						else 0
					local stagger: string = pz.stagger
					local attackerHum: Humanoid = ah
					local parryTrack = vs.track
					-- the stun COVERS the riposte: the attacker is still reeling when the answer lands, + 0.3 s for
					-- the stagger to read (a stun ending with the riposte lost the stagger to any frame hitch - the
					-- Studio playtest, 2026-10-24: 0.44 s due vs a 0.6 s stun, skipped at a slow server's 0.16 s frames)
					-- (capped at PARRY_COVER_MAX: a parry clip with a long wind-up never freezes the attacker for good)
					local base = s.stunnedUntil
					local cover = math.min(delay + math.max(0, o.hitstop) + 0.3, PARRY_COVER_MAX)
					local covered = math.max(base, now + cover)
					s.stunnedUntil = covered
					task.delay(math.min(delay + math.max(0, o.hitstop), cover), function()
						-- only while the attacker is still stunned and idle (a stun shorter than the wait lets it act
						-- again) and the defender's riposte was not cut off by a hit of its own
						if
							attackerHum.Parent
							and attackerHum.Health > 0
							and gameNow() < s.stunnedUntil
							and not s.move
							and vs.track == parryTrack
						then
							if s.track then
								s.track:Stop(0.05)
							end
							s.track = playAtMarker(attackerHum, stagger, "Hit")
						elseif s.stunnedUntil == covered then
							-- no riposte came (cut off): the cover is given back - the attacker keeps only its own stun
							s.stunnedUntil = math.max(base, gameNow())
						end
					end)
				end
			end
			local Sfx2 = Sfx
			if Sfx2 then
				Sfx2.broadcast("SwordParry", pos)
			end
			hitstop(vs, o.hitstop)
			return
		end
		if o.kind == "dodged" then
			return
		end
		-- the contact's SOUND and VFX leave in the same instant as its Bus event, BEFORE the victim's reaction is loaded
		-- and started (that load can take a frame or more: with them after it, the hit sound reached the clients a
		-- network send after the hit - 173 ms on a background Studio server - tests/playtest/kit_integration_arena,
		-- 2026-11-21; LIMITATIONS_FIXES_V4 13.8: the A/V offset <= 16.7 ms)
		if Sfx then
			if o.kind == "hit" and type(onHit.sfx) == "string" then
				Sfx.broadcast(
					onHit.sfx,
					pos,
					{ weight = onHit.weight, surface = victim:GetAttribute("KitSurface") or "flesh" }
				)
			elseif o.kind ~= "hit" then
				Sfx.broadcast("SwordBlock", pos)
			end
		end
		if Vfx and o.kind == "hit" and type(onHit.vfx) == "string" then
			Vfx.broadcast(onHit.vfx, pos)
		end
		if o.damage > 0 then
			local before = vh.Health
			vh:TakeDamage(o.damage)
			if Bus and before > 0 and vh.Health <= 0 then
				Bus.publish(
					"Death",
					{ victim = victim, attacker = attacker, move = s.moveName, at = pos },
					{ near = 400 }
				)
			end
		end
		vs.stunnedUntil = math.max(vs.stunnedUntil, now + o.stun)
		victim:SetAttribute("KitStunnedUntil", vs.stunnedUntil)
		if vs.move and o.kind == "hit" then
			if vs.track then
				vs.track:Stop(0.05)
			end
			vs.move, vs.moveName = nil, nil -- a clean hit interrupts the victim's own move
		end
		knockback(victim, aroot, o.knockback)
		-- BOTH-SIDED IMPACT (AAA gaps v2 C4): the victim's reaction - `onHit.reaction`, by the side the blow came from
		-- (the most specific of <reaction>Air / <reaction><Side><Tier> / <Side> / <Tier> that exists), started AT its own Hit marker - then
		-- frozen with the attacker by the same hit-stop, so both bodies hold the contact before the recoil
		if Anim and o.kind == "hit" and type(onHit.reaction) == "string" then
			local vroot = rootOf(victim)
			if vroot then
				local side = AnimLayers.reactionSide(
					aroot.Position.X,
					aroot.Position.Z,
					vroot.Position.X,
					vroot.Position.Z,
					vroot.CFrame.LookVector.X,
					vroot.CFrame.LookVector.Z
				)
				local meta: any = Anim.meta()
				-- the matrix (C3): by side, the move's tier (light / medium / heavy) and whether the victim is airborne
				local airborne = vh.FloorMaterial == Enum.Material.Air
				local tier = if type(onHit.tier) == "string" then onHit.tier else (s.move :: any).tier
				local name = AnimLayers.reactionName(onHit.reaction, side, tier, airborne, function(n: string): boolean
					return meta[n] ~= nil
				end)
				if vs.track then
					vs.track:Stop(0.02)
				end
				vs.track = playAtMarker(vh, name, "Hit")
			end
		end
		-- a KNOCKDOWN (AAA gaps v2 D13): the body goes limp (physics) for `onHit.knockdown` seconds, then stands
		if o.kind == "hit" and type(onHit.knockdown) == "number" and onHit.knockdown > 0 then
			local Ragdoll = optional("AnimRagdoll")
			if Ragdoll then
				local kb = o.knockback or { 0, 0, 0 }
				local push = aroot.CFrame.RightVector * kb[1] + Vector3.yAxis * kb[2] + aroot.CFrame.LookVector * kb[3]
				-- (onHit.getUp = { back = "<clip>", front = "<clip>" }: the get-up it plays; onHit.getUpBlend: seconds)
				Ragdoll.knock(victim, push, onHit.knockdown, { getUp = onHit.getUp, blend = onHit.getUpBlend })
			end
		end
		hitstop(s, o.hitstop)
		hitstop(vs, o.hitstop)
	end

	local debugParts: { BasePart } = {}
	-- every hitbox in `boxes`, on the attacker's root now: each victim hit once per move
	local function hitWith(character: Model, s: State, root: BasePart, boxes: { any })
		local params = OverlapParams.new()
		params.FilterType = Enum.RaycastFilterType.Exclude
		params.FilterDescendantsInstances = { character }
		for _, hb in boxes do
			local off = hb.offset or { 0, 0, 0 }
			local cf = root.CFrame * CFrame.new(off[1], off[2], off[3])
			local size = Vector3.new(hb.size[1], hb.size[2], hb.size[3])
			if debugOn then
				local p = Instance.new("Part")
				p.Anchored, p.CanCollide, p.CanQuery, p.CanTouch = true, false, false, false
				p.Transparency, p.Color, p.Size, p.CFrame = 0.6, Color3.fromRGB(255, 60, 60), size, cf
				p.Parent = Workspace
				table.insert(debugParts, p)
			end
			for _, part in Workspace:GetPartBoundsInBox(cf, size, params) do
				local model = part:FindFirstAncestorOfClass("Model")
				if model and not s.hit[model] and model:FindFirstChildOfClass("Humanoid") then
					s.hit[model] = true -- one hit per victim per move
					apply(character, s, model)
				end
			end
		end
	end

	RunService.Heartbeat:Connect(function()
		for _, p in debugParts do
			p:Destroy()
		end
		table.clear(debugParts)
		local now = gameNow()
		-- a snapshot: a first hit on a fresh NPC adds its state to `states` inside this loop
		local chars: { Model } = {}
		for character in states do
			table.insert(chars, character)
		end
		for _, character in chars do
			local s = states[character]
			if not s then
				continue
			end
			local queued = s.buffered
			if queued and now >= s.hitstopUntil and now >= s.stunnedUntil then
				if not s.move or moveTime(s, now) >= queued.moveAt then
					s.buffered = nil
					if now - queued.made < BUFFER_STALE then -- (a press held through a long stun goes stale)
						use(character, queued.name)
					end
				end
			end
			local move = s.move
			if not move then
				continue
			end
			if now < s.hitstopUntil then
				continue -- the move's clock is frozen during hit-stop
			end
			local t = moveTime(s, now)
			local phase, frame = MovesRules.phaseAt(move, t)
			-- every hitbox live on a frame passed since the last step (a late step - a server hitch - never skips a
			-- hit window; MovesRules.hitboxesBetween)
			local from = s.checkedFrame or -1
			s.checkedFrame = math.max(from, frame)
			local boxes = MovesRules.hitboxesBetween(move, from, frame)
			-- (a move that ended inside this late step still lands its last hits first: apply reads s.move)
			local root = if #boxes > 0 then rootOf(character) else nil
			if root then
				hitWith(character, s, root, boxes)
			end
			if phase == "done" and s.move == move then
				s.lastName, s.lastEnded = s.moveName, now
				s.move, s.moveName = nil, nil
			end
		end
	end)

	useRemote.OnServerEvent:Connect(function(player: Player, rawName: unknown)
		if not useLimit:take(player.UserId, os.clock()) then
			return
		end
		local ok, name = Guard.oneOf(rawName, names)
		local character = player.Character
		if ok and character then
			use(character, name)
		end
	end)
	defendRemote.OnServerEvent:Connect(function(player: Player, rawKind: unknown, rawOn: unknown)
		if not defendLimit:take(player.UserId, os.clock()) then
			return
		end
		local okKind, kind = Guard.oneOf(rawKind, { "block", "parry" })
		local okOn, on = Guard.boolean(rawOn)
		local character = player.Character
		if not okKind or not okOn or not character then
			return
		end
		local s = stateOf(character)
		if gameNow() < s.stunnedUntil or s.move then
			return -- no blocking while stunned or mid-move
		end
		if kind == "parry" then
			local now = gameNow()
			if not MovesRules.parryAllowed(s.parryAt, now) then
				return -- the lockout after a parry: no window held open by spamming
			end
			s.parryAt = now -- a parry is its window only (MovesRules), never a block that stays on
		else
			s.blocking = on
		end
	end)
	Players.PlayerRemoving:Connect(function(p: Player)
		useLimit:forget(p.UserId)
		defendLimit:forget(p.UserId)
	end)

	local handle = {
		use = use,
		state = function(character: Model): State
			return stateOf(character)
		end,
		hits = hitEvent.Event, -- served.hits:Connect(function(contact) ... end)
	}
	served[setName] = handle
	return handle
end

-- the handle a set was served with (NPCs, dummies that fight back, playtests): nil until Moves.serve(setName)
function Moves.get(setName: string): any?
	return served[setName]
end

function Moves.debug(on: boolean)
	debugOn = on
end

-- ---------------------------------------------------------------- client
function Moves.client(setName: string)
	assert(not RunService:IsServer(), "Moves.client is client-only")
	local useRemote, defendRemote = remotes(setName)
	return {
		use = function(name: string)
			useRemote:FireServer(name)
		end,
		block = function(on: boolean)
			defendRemote:FireServer("block", on)
		end,
		parry = function()
			defendRemote:FireServer("parry", true)
		end,
	}
end

return Moves

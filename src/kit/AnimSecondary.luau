--!strict
-- AnimSecondary — SECONDARY MOTION on accessories (AAA gaps v2 D7; spring bones: hair, a cape, a sheath, a tassel move
-- on their own - stiffness, damping and gravity instead of keys). Each accessory's weld gets a tilt driven by the
-- body's acceleration through a damped spring (src/kit/AnimLayers.sway: the rule of one frame, spec'd), so the
-- accessory lags behind a start and a stop and settles. Runs on the client that sees it (cosmetic: nothing
-- replicates). WHICH WAY an accessory tips has not been seen: the spec only holds that a start and a stop tip it
-- opposite ways.
--
--   local stop = AnimSecondary.attach(character, { stiffness = 60, damping = 0.45, gain = 0.02, max = 25 })
--
-- BY KIND, WITH LIMITS AND TIERS (the owner's older list, AN-31; the rules are AnimLayers.swayClass / swayLimit /
-- swayPush / swayTier): hair, a cape, a sheath and a hat each get their own spring and their own limits - small on
-- the body's side, the stand-in for collision (a worn accessory does not collide); what sits on the face or is
-- clothing does not sway; a teleport's one-frame push is held; far from the camera an accessory is stepped every
-- other frame, further still not at all. Options a game gives (stiffness / damping / gain) replace the class's;
-- `max` caps every limit; `near` / `far` (studs) move the tiers.
--
-- THE WAY IN: the kit's client script (src/kit/client/AnimRoot.client.luau) attaches it to every player's character
-- when the game asks for it - set the attribute KitSecondary = true on ReplicatedStorage.kit (a table of the options
-- above as attributes KitSecondaryStiffness / Damping / Gain / Max is optional). Off unless asked: it changes how
-- every accessory moves. The attributes are read when a character appears: a change shows after a respawn.
-- An accessory that arrives after its character (Roblox adds them late) is picked up when it arrives; a character
-- taken out of the world stops by itself.
--
-- Studio-unproven (written 2026-10-22).

local RunService = game:GetService("RunService")
local AnimLayers = require(script.Parent.AnimLayers)

local AnimSecondary = {}

export type Options = { stiffness: number?, damping: number?, gain: number?, max: number?, near: number?, far: number? }

function AnimSecondary.attach(character: Model, opts: Options?): () -> ()
	local o: Options = opts or {}
	local root = character:FindFirstChild("HumanoidRootPart")
	if not root or not root:IsA("BasePart") then
		return function() end
	end
	local rootPart = root :: BasePart
	local welds: {
		{
			weld: Weld,
			side: string,
			base: CFrame,
			sx: AnimLayers.Swing,
			sz: AnimLayers.Swing,
			class: AnimLayers.SwayClass,
			spring: AnimLayers.SwayOptions,
			hip: number,
			hangs: boolean,
			front: boolean,
		}
	} =
		{}
	local seen: { [Weld]: boolean } = {}
	-- an accessory's weld: a Weld that joins the Handle of an Accessory of this character to its body - WHEREVER the
	-- engine put it (seen in Studio 2026-11-15: an accessory with attachments gets "AccessoryWeld" under its Handle;
	-- one without gets a Weld under the BODY part, "HeadWeld" under the Head - only the first was found)
	local function handleOf(part: BasePart?): boolean
		return part ~= nil
			and part.Name == "Handle"
			and part.Parent ~= nil
			and part.Parent:IsA("Accessory")
			and part:IsDescendantOf(character)
	end
	-- a part of the BODY: straight under the character, not inside an accessory
	local function bodyPart(part: BasePart?): boolean
		return part ~= nil and part.Parent == character
	end
	local function take(w: Instance)
		if not w:IsA("Weld") or seen[w] then
			return
		end
		-- (a weld between two parts of one accessory, or between two accessories, is not taken: only the one that
		-- hangs the handle on the body)
		local side = AnimLayers.weldSide(handleOf(w.Part0), handleOf(w.Part1), bodyPart(w.Part0), bodyPart(w.Part1))
		if side then
			seen[w] = true
			local handle = if side == "C0" then w.Part1 else w.Part0
			local accessory = handle and handle.Parent
			local kind = if accessory and accessory:IsA("Accessory") then accessory.AccessoryType.Name else nil
			local base = if side == "C0" then w.C0 else w.C1
			local other = if side == "C0" then w.C1 else w.C0
			-- where the accessory's own middle is, in the body part's space (from the weld's two frames: the handle's
			-- place in the world is not solved yet when a weld is first seen - Studio, 2026-11-15)
			local middle = (base * other:Inverse()).Position
			local hangs = middle.Y < base.Position.Y - 0.05
			local class = AnimLayers.swayClass(kind)
			-- (most legacy accessories are typed Hat or Unknown whatever they are: one that hangs down behind the
			-- body is a cape or a pack, and moves as one)
			if (kind == "Hat" or kind == "Unknown" or kind == nil) and hangs and middle.Z > 0.3 then
				class = AnimLayers.swayClass("Back")
			end
			if not class then
				return -- (it sits on the face or is clothing: it does not sway)
			end
			table.insert(welds, {
				weld = w,
				side = side,
				base = base,
				sx = { x = 0, v = 0 },
				sz = { x = 0, v = 0 },
				class = class,
				-- (the class's spring, a game's own numbers over it; the limit is the class's: `max` 1000 keeps sway's own
				-- clamp out of the way)
				spring = {
					stiffness = o.stiffness or class.stiffness,
					damping = o.damping or class.damping,
					gain = o.gain or class.gain,
					max = 1000,
				},
				-- which hip: where the body's side of the weld sits, right (+) or left (-) of the body part's middle
				-- which hip: where the accessory's own middle is, right (+) or left (-) of the body part's (the R6's
				-- waist attachments all sit in the middle: the attach point says nothing - the one review)
				hip = if math.abs(middle.X) < 0.25 then 0 else math.sign(middle.X),
				front = middle.Z < -0.3, -- it hangs in front of the body: the body is behind it
				-- does it hang below where it is worn, or stand up from it? Its own middle against its attach point, in
				-- the body part's space - from the weld's own two frames (the handle's place in the world is not solved
				-- yet when a weld is first seen: Studio, 2026-11-15)
				hangs = hangs,
			})
		end
	end
	for _, d in character:GetDescendants() do
		take(d)
	end
	-- (Roblox adds a character's accessories after it appears; a weld may be parented before its parts are set:
	-- it is looked at once more a moment later)
	local added = character.DescendantAdded:Connect(function(w: Instance)
		take(w)
		task.defer(take, w)
	end)
	local lastV = rootPart.AssemblyLinearVelocity
	local smoothed = Vector3.zero
	local stopped = false
	local frame, owed, resting = 0, 0, false
	local conn: RBXScriptConnection
	local function stop()
		if stopped then
			return
		end
		stopped = true
		conn:Disconnect()
		added:Disconnect()
		for _, s in welds do
			if s.weld.Parent then
				if s.side == "C0" then
					s.weld.C0 = s.base
				else
					s.weld.C1 = s.base
				end
			end
		end
	end
	conn = RunService.Stepped:Connect(function(_, dt: number)
		if character.Parent == nil or not rootPart.Parent then
			stop() -- (a character taken out of the world: nothing keeps running on it, whether or not it is destroyed)
			return
		end
		local v = rootPart.AssemblyLinearVelocity
		if dt <= 0 then
			lastV = v
			return
		end
		local a = rootPart.CFrame:VectorToObjectSpace((v - lastV) / dt) -- character space acceleration
		lastV = v
		-- (a teleport's one-frame push is no push: held to what a body can give)
		local px, pz = AnimLayers.swayPush(a.X, a.Z)
		-- (another player's velocity arrives in steps: eased, so their accessories do not twitch on every packet)
		smoothed += (Vector3.new(px, 0, pz) - smoothed) * (1 - math.exp(-dt * 20))
		-- THE TIER: by how far the camera is - every frame, every other frame (the time between summed), or not at
		-- all (the accessories put back as they are worn, once)
		-- (only a CLIENT's camera is somebody's eye: a server has one too, parked far away - seen in Studio, 224 studs,
		-- where it switched every accessory off)
		local cam = if RunService:IsClient() then workspace.CurrentCamera else nil
		local every =
			AnimLayers.swayTier(if cam then (cam.CFrame.Position - rootPart.Position).Magnitude else nil, o.near, o.far)
		if every == 0 then
			if not resting then
				resting = true
				for _, s in welds do
					s.sx, s.sz = { x = 0, v = 0 }, { x = 0, v = 0 }
					if s.weld.Parent then
						if s.side == "C0" then
							s.weld.C0 = s.base
						else
							s.weld.C1 = s.base
						end
					end
				end
			end
			return
		end
		resting = false
		frame += 1
		owed += dt
		if frame % every ~= 0 then
			return
		end
		-- (sway moves nothing on a step over a tenth of a second: a longer wait is stepped in tenths, at most three -
		-- a slow machine's spring keeps its own time, a real hitch is capped)
		local due = math.min(owed, 0.3)
		owed = 0
		for _, s in welds do
			local rx, rz = 0, 0
			local left = due
			while left > 1e-6 do
				local step = math.min(left, 0.1)
				left -= step
				s.sx, s.sz, rx, rz = AnimLayers.sway(s.sx, s.sz, smoothed.X, smoothed.Z, step, s.spring) -- (the rule of one frame, spec'd)
			end
			rx, rz = AnimLayers.swayHang(rx, rz, s.hangs)
			rx, rz = AnimLayers.swayLimit(rx, rz, s.class, s.hip, o.max, s.front)
			if s.weld.Parent then
				-- (the tilt is put on the BODY's side of the weld: it pivots at the body's attach point and tips the
				-- same way whichever part the engine made Part0)
				-- about the BODY part's own axes at the attach point (an attachment that is itself turned would
				-- otherwise swing, and be limited, about its own)
				local tilted = CFrame.new(s.base.Position) * CFrame.Angles(rx, 0, rz) * s.base.Rotation
				if s.side == "C0" then
					s.weld.C0 = tilted
				else
					s.weld.C1 = tilted
				end
			end
		end
	end)
	return stop
end

return AnimSecondary

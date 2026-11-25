--!strict
-- AnimLife (ReplicatedStorage.kit.AnimLife) — THE LIFECYCLE OF THE RUNTIME LAYERS A CLIENT RUNS FOR A CHARACTER (the
-- owner's limitations list, 2026-11-15, A-R01: "several new runtime methods lack demonstrated game integration ...
-- wire the intended client callers and lifecycle ... respawn, interruption"). Foot placement, a motion set, secondary
-- motion, the get-up watch, a crowd's tracking: each is started for a character and hands back a stop. This keeps
-- them: one of a kind per character, all stopped when the character is gone (a respawn, a leave), stood down while
-- the body is not the animation's (a ragdoll, a cutscene) and brought back after.
--   local life = AnimLife.new()
--   life:start(character, "feet", function() return Anim.feet(character) end, { suspends = true })
--   life:suspend(character, "down")      -- a ragdoll took the body: every layer that `suspends` is stopped
--   life:resume(character, "down")       -- the last reason is gone: those layers are started again
--   life:clear(character)                -- it respawned or left: everything is stopped and forgotten
-- PURE: no instances, no services (an owner is any key). The caller: src/kit/client/AnimRoot.client.luau.
-- WRITTEN, NEVER SEEN TO MOVE: that a real Animator, a real respawn and several watching clients behave is Studio's.
local AnimLife = {}
AnimLife.__index = AnimLife

export type Start = () -> (() -> ())?
export type Options = { suspends: boolean? }
type Layer = { start: Start, stop: (() -> ())?, suspends: boolean }
type Owner = { layers: { [string]: Layer }, reasons: { [string]: boolean } }
export type Life = typeof(setmetatable({} :: { owners: { [any]: Owner }, errors: { string } }, AnimLife))

function AnimLife.new(): Life
	return setmetatable({ owners = setmetatable({}, { __mode = "k" }) :: any, errors = {} }, AnimLife)
end

local function note(self: Life, what: string, err: any)
	table.insert(self.errors, `{what}: {tostring(err)}`)
	if #self.errors > 20 then
		table.remove(self.errors, 1)
	end
end

local function down(o: Owner): boolean
	return next(o.reasons) ~= nil
end

-- a layer's own stop, called once; one that throws does not keep the others from being stopped
local function halt(self: Life, name: string, layer: Layer)
	local stop = layer.stop
	layer.stop = nil
	if stop then
		local ok, err = pcall(stop :: any)
		if not ok then
			note(self, `stopping {name}`, err)
		end
	end
end

-- (a start may YIELD - it waits for a part, a module: by the time it hands its stop back the owner may be gone, the
-- layer replaced or the body down. Then the layer it just started is stopped at once: nothing runs unowned)
local function run(self: Life, owner: any, o: Owner, name: string, layer: Layer)
	local ok, stop = pcall(layer.start)
	if not ok then
		note(self, `starting {name}`, stop)
		return
	end
	layer.stop = if type(stop) == "function" then stop else nil
	if self.owners[owner] ~= o or o.layers[name] ~= layer or (layer.suspends and down(o)) then
		halt(self, name, layer)
	end
end

-- START a layer for an owner. One of a name per owner: started again, the old one is stopped first. While the owner
-- is stood down, a layer that `suspends` is only remembered - it starts when the owner is resumed. -> is it running?
function AnimLife.start(self: Life, owner: any, name: string, start: Start, opts: Options?): boolean
	local o = self.owners[owner]
	if not o then
		o = { layers = {}, reasons = {} }
		self.owners[owner] = o
	end
	local old = o.layers[name]
	if old then
		halt(self, name, old)
	end
	local layer: Layer = { start = start, stop = nil, suspends = opts ~= nil and opts.suspends == true }
	o.layers[name] = layer
	if layer.suspends and down(o) then
		return false
	end
	run(self, owner, o, name, layer)
	return layer.stop ~= nil
end

-- STOP one layer of an owner and forget it
function AnimLife.stop(self: Life, owner: any, name: string)
	local o = self.owners[owner]
	local layer = if o then o.layers[name] else nil
	if o and layer then
		halt(self, name, layer)
		o.layers[name] = nil
	end
end

-- THE OWNER IS GONE (a respawn, a leave, a death): every layer is stopped, nothing is remembered - not what was
-- stood down either (the new character starts its own)
function AnimLife.clear(self: Life, owner: any)
	local o = self.owners[owner]
	if not o then
		return
	end
	self.owners[owner] = nil
	for name, layer in o.layers do
		halt(self, name, layer)
	end
end

-- THE BODY IS NOT THE ANIMATION'S for a while (`reason`: a ragdoll, a cutscene, a stun that poses it): every layer
-- that `suspends` is stopped. Reasons add up: the layers come back when the LAST one is resumed.
function AnimLife.suspend(self: Life, owner: any, reason: string)
	local o = self.owners[owner]
	if not o then
		o = { layers = {}, reasons = {} }
		self.owners[owner] = o
	end
	local was = down(o)
	o.reasons[reason] = true
	if not was then
		for name, layer in o.layers do
			if layer.suspends then
				halt(self, name, layer)
			end
		end
	end
end

function AnimLife.resume(self: Life, owner: any, reason: string)
	local o = self.owners[owner]
	if not o or not o.reasons[reason] then
		return
	end
	o.reasons[reason] = nil
	if not down(o) then
		for name, layer in o.layers do
			if layer.suspends and not layer.stop then
				run(self, owner, o, name, layer)
			end
		end
	end
end

-- is this layer of this owner running now?
function AnimLife.running(self: Life, owner: any, name: string): boolean
	local o = self.owners[owner]
	local layer = if o then o.layers[name] else nil
	return layer ~= nil and layer.stop ~= nil
end

-- how many layers run now, over every owner
function AnimLife.count(self: Life): number
	local n = 0
	for _, o in self.owners do
		for _, layer in o.layers do
			if layer.stop then
				n += 1
			end
		end
	end
	return n
end

-- WHICH HUMANOID STATES take the body from the animation ("down") - by the state's NAME, so the rule is the kit's to
-- test: a ragdoll or a knockdown (Physics, Ragdoll, FallingDown, PlatformStanding), GETTING UP from one (the get-up
-- blend still writes the hips: foot placement on the same joints would stack on it) and death
AnimLife.DOWN =
	{ Physics = true, Ragdoll = true, FallingDown = true, PlatformStanding = true, GettingUp = true, Dead = true }

function AnimLife.isDown(stateName: string): boolean
	return AnimLife.DOWN[stateName] == true
end

return AnimLife

--!strict
-- VfxMood (kit) — ONE stack for what effects do to the client's Lighting and Atmosphere (the V3 doc, VFX stage B:
-- "a ref-counted priority mood stack").
--
-- Before: every world layer and every impact frame saved the Lighting it found when it started and wrote that back
-- when it ended. Two at once fought: the second saved the first one's darkened sky, and whichever ended last wrote
-- its own snapshot back - a mood could stay after both were gone. And an impact frame set Lighting.FogEnd = 1, which
-- the engine ignores whenever an Atmosphere exists (most places have one): the paper never came.
--
-- Now each effect PUSHES the values it wants under its own id and a priority; the stack writes, per value, the one
-- of the highest priority (ties: the latest pushed). The scene's own value of a key is read ONCE - the first time
-- any effect asks for that key while none is holding it - and written back when the last effect holding it lets go.
-- Pure: the caller hands in how a key is read and written (VfxStage: Lighting and its Atmosphere), so the rule is
-- tested without the engine (kit/test/spec/vfxmood.spec.luau).
local VfxMood = {}
VfxMood.__index = VfxMood

-- the value a key had when there was nothing to read (no Atmosphere): never written back
local NONE = newproxy(false)

export type Mood = typeof(setmetatable(
	{} :: {
		read: (string) -> any,
		write: (string, any) -> (),
		entries: { [any]: { priority: number, seq: number, values: { [string]: any } } },
		base: { [string]: any },
		seq: number,
	},
	VfxMood
))

function VfxMood.new(read: (string) -> any, write: (string, any) -> ()): Mood
	return setmetatable({ read = read, write = write, entries = {}, base = {}, seq = 0 }, VfxMood)
end

-- the scene's own value of a key: the one read before any effect touched it (nil when there is nothing to read)
function VfxMood.baseOf(self: Mood, key: string): any
	local b = self.base[key]
	if b == nil then
		b = self.read(key)
		if b == nil then
			return nil
		end
		return b
	end
	return if b == NONE then nil else b
end

-- the value that wins a key now: the highest priority entry holding it, the latest pushed on a tie
local function winner(self: Mood, key: string): (boolean, any)
	local best, bestP, bestS = nil, -math.huge, -1
	for _, e in self.entries do
		local v = e.values[key]
		if v ~= nil and (e.priority > bestP or (e.priority == bestP and e.seq > bestS)) then
			best, bestP, bestS = v, e.priority, e.seq
		end
	end
	return best ~= nil, best
end

local function apply(self: Mood, keys: { [string]: boolean })
	for key in keys do
		local held, v = winner(self, key)
		if held then
			self.write(key, v)
		else
			local b = self.base[key]
			self.base[key] = nil -- nothing holds it any more: the next push reads the scene again
			if b ~= nil and b ~= NONE then
				self.write(key, b)
			end
		end
	end
end

-- id wants these values (replacing what it wanted before), at this priority (an impact frame over a world layer)
function VfxMood.push(self: Mood, id: any, priority: number, values: { [string]: any })
	local touched: { [string]: boolean } = {}
	for key in values do
		if self.base[key] == nil then
			local b = self.read(key)
			self.base[key] = if b == nil then NONE else b
		end
		touched[key] = true
	end
	local e = self.entries[id]
	if e then
		for key in e.values do
			touched[key] = true -- a key it no longer wants goes back to the next one down
		end
		e.priority, e.values = priority, values
	else
		self.seq += 1
		self.entries[id] = { priority = priority, seq = self.seq, values = values }
	end
	apply(self, touched)
end

-- id lets go of everything it held (an unknown id: nothing happens)
function VfxMood.pop(self: Mood, id: any)
	local e = self.entries[id]
	if not e then
		return
	end
	self.entries[id] = nil
	local touched: { [string]: boolean } = {}
	for key in e.values do
		touched[key] = true
	end
	apply(self, touched)
end

-- how many effects hold the mood now (0: the scene is its own again)
function VfxMood.holders(self: Mood): number
	local n = 0
	for _ in self.entries do
		n += 1
	end
	return n
end

return VfxMood

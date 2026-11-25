--!strict
-- VfxHighlight (kit) — who may light a Highlight when the client has only 31 (the V3 doc, VFX stage B: "a priority
-- Highlight allocator").
--
-- The engine draws at most 31 Highlights on a client (the 32nd and on are simply not drawn: which one is lost is
-- the engine's pick). The VFX runtime made one per highlight layer, per impact-frame silhouette and per effect's
-- outlines with no count at all: a busy fight lost the attacker's or the victim's rim to a distant spark's outline.
--
-- Now every Highlight the runtime turns ON claims a slot first, with a priority: HERO (the fighter's own aura, the
-- impact frame's silhouettes, a boss) may take any slot; anything lower may hold at most CAP - RESERVED of them,
-- so 24 always stay for heroes. A hero claim on a full client takes the slot of the lowest-priority holder (the
-- oldest on a tie) and says which, so its owner turns it off; a claim that cannot be met is refused (the layer
-- stays off this frame and asks again the next). Pure: tested in kit/test/spec/vfxhighlight.spec.luau.
local VfxHighlight = {}
VfxHighlight.__index = VfxHighlight

VfxHighlight.CAP = 31 -- the engine's own limit per client
VfxHighlight.RESERVED = 24 -- slots only a HERO claim may take
VfxHighlight.AMBIENT = 1 -- an effect's outlines, a far spark's rim
VfxHighlight.HERO = 2 -- the fighter's own aura, the victim, a boss, the impact frame's silhouettes

export type Slots = typeof(setmetatable(
	{} :: {
		cap: number,
		reserved: number,
		held: { [any]: { priority: number, seq: number } },
		seq: number,
	},
	VfxHighlight
))

function VfxHighlight.new(cap: number?, reserved: number?): Slots
	local c = cap or VfxHighlight.CAP
	return setmetatable({
		cap = c,
		reserved = math.min(reserved or VfxHighlight.RESERVED, c),
		held = {},
		seq = 0,
	}, VfxHighlight)
end

function VfxHighlight.count(self: Slots, below: number?): number
	local n = 0
	for _, h in self.held do
		if below == nil or h.priority < below then
			n += 1
		end
	end
	return n
end

-- the holder a claim at this priority may take the place of: the lowest priority under it, the oldest on a tie
local function weakest(self: Slots, under: number): any
	local pick, pp, ps = nil, math.huge, math.huge
	for id, h in self.held do
		if h.priority < under and (h.priority < pp or (h.priority == pp and h.seq < ps)) then
			pick, pp, ps = id, h.priority, h.seq
		end
	end
	return pick
end

-- id wants to be drawn -> (granted, the id whose slot it took or nil). Claiming again while holding is a yes.
function VfxHighlight.claim(self: Slots, id: any, priority: number): (boolean, any)
	if self.held[id] then
		self.held[id].priority = priority
		return true, nil
	end
	local function take(): (boolean, any)
		self.seq += 1
		self.held[id] = { priority = priority, seq = self.seq }
		return true, nil
	end
	local total = VfxHighlight.count(self)
	if priority >= VfxHighlight.HERO then
		if total < self.cap then
			return take()
		end
	else
		local lowCap = self.cap - self.reserved
		if total < self.cap and VfxHighlight.count(self, VfxHighlight.HERO) < lowCap then
			return take()
		end
	end
	-- full (for this priority): take the place of a lower one
	local loser = weakest(self, priority)
	if loser == nil then
		return false, nil
	end
	self.held[loser] = nil
	local ok = take()
	return ok, loser
end

function VfxHighlight.release(self: Slots, id: any)
	self.held[id] = nil
end

function VfxHighlight.holds(self: Slots, id: any): boolean
	return self.held[id] ~= nil
end

return VfxHighlight

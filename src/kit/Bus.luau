--!strict
-- Bus.luau — the PRESENTATION EVENT BUS (mission 06, idea 10: the "juice layer"). Gameplay says WHAT happened
-- (Hit, Blocked, Chip, Parried, Death, ...); feel, VFX, SFX and UI subscribe and decide how it LOOKS and SOUNDS.
-- A system never calls a presentation module by name, so a game without one still plays.
--
--   local Bus = require(ReplicatedStorage.kit.Bus)
--   server:  Bus.publish("Hit", { attacker = a, victim = v, damage = 12, at = pos, weight = 0.6 }, { near = 120 })
--   client:  Bus.start()   -- once; then  Bus.on("Hit", function(e) ... end)   (also on the server, for server feel)
--
-- The core (Bus.new: on / once / emit, "*" hears every event) is pure; each listener runs isolated (one that errors is
-- reported and the rest still run). Replication is ONE RemoteEvent the server fires and clients only listen to:
-- clients can never publish (no server handler exists, nothing to exploit). `near` sends only to players within that
-- many studs of `at`.
local Bus = {}
local Core = {}
Core.__index = Core

export type Listener = (payload: any, name: string) -> ()

-- a bus of its own (the shared one is Bus.shared)
function Bus.new(report: ((string) -> ())?)
	local self = setmetatable({}, Core) :: any
	self.listeners = {} :: { [string]: { Listener } }
	self.report = report or function(text: string)
		warn(text)
	end
	return self
end

-- listen to `name` ("*" = every event); returns the function that stops listening
function Core.on(self: any, name: string, fn: Listener): () -> ()
	local list = self.listeners[name]
	if not list then
		list = {}
		self.listeners[name] = list
	end
	table.insert(list, fn)
	return function()
		local i = table.find(list, fn)
		if i then
			table.remove(list, i)
		end
	end
end

function Core.once(self: any, name: string, fn: Listener): () -> ()
	local stop: (() -> ())? = nil
	stop = self:on(name, function(payload: any, n: string)
		if stop then
			stop()
		end
		fn(payload, n)
	end)
	return stop :: () -> ()
end

-- every listener of `name`, then every "*" listener; a listener added while emitting hears the NEXT event
function Core.emit(self: any, name: string, payload: any)
	for _, key in { name, "*" } do
		local list: { Listener }? = self.listeners[key]
		if list then
			local snapshot: { Listener } = table.clone(list)
			for _, fn in snapshot do
				local result = table.pack(pcall(fn, payload, name))
				if not result[1] then
					self.report(`[Bus] a "{name}" listener failed: {result[2]}`)
				end
			end
		end
	end
end

-- ------------------------------------------------------------------ the shared bus, replicated
Bus.shared = Bus.new()
Bus.REMOTE = "KitBus"

local function services(): (any, any, any)
	local ok, rs = pcall(function()
		return (game :: any):GetService("ReplicatedStorage")
	end)
	if not ok then
		return nil, nil, nil
	end
	local g = game :: any
	return rs, g:GetService("RunService"), g:GetService("Players")
end

local function remote(create: boolean): any
	local rs = services()
	if not rs then
		return nil
	end
	local r = rs:FindFirstChild(Bus.REMOTE)
	if not r and create then
		r = Instance.new("RemoteEvent")
		r.Name = Bus.REMOTE
		r.Parent = rs
	end
	return r
end

-- the players a publish reaches: everyone, or those within `near` studs of payload.at
function Bus.audience(players: { any }, at: Vector3?, near: number?): { any }
	if not near or not at then
		return players
	end
	local out = {}
	for _, p in players do
		local ch = p.Character
		local root = ch and ch:FindFirstChild("HumanoidRootPart")
		if root and (root.Position - at).Magnitude <= near then
			table.insert(out, p)
		end
	end
	return out
end

-- server: tell the server's listeners and the clients (all, or `near` = within that many studs of payload.at)
function Bus.publish(name: string, payload: any, opts: { near: number? }?)
	Bus.shared:emit(name, payload)
	local _, RunService, Players = services()
	if not RunService or not RunService:IsServer() then
		return
	end
	local r = remote(true)
	local at = if type(payload) == "table" and typeof(payload.at) == "Vector3" then payload.at else nil
	for _, p in Bus.audience(Players:GetPlayers(), at, opts and opts.near) do
		r:FireClient(p, name, payload)
	end
end

-- the shared bus: listen anywhere (server feel, client presentation)
function Bus.on(name: string, fn: Listener): () -> ()
	return Bus.shared:on(name, fn)
end

function Bus.once(name: string, fn: Listener): () -> ()
	return Bus.shared:once(name, fn)
end

-- client: hear the server's events (once per client; safe to call twice)
local started = false
function Bus.start()
	if started then
		return
	end
	local rs, RunService = services()
	if not rs or RunService:IsServer() then
		return
	end
	started = true
	-- (the server makes the remote on its FIRST publish - the first contact - so a client that starts before any hit
	-- waits for it in a thread of its own: the caller is never held up, and a timeout of math.huge never logs
	-- "Infinite yield possible". Before: the SampleDojo's CombatController stopped at Bus.start() and the console turned
	-- red 5 s into every session nobody had hit anything - the Studio red-team playtest, 2026-11-20)
	task.spawn(function()
		local r = rs:WaitForChild(Bus.REMOTE, math.huge)
		r.OnClientEvent:Connect(function(name: unknown, payload: unknown)
			if type(name) == "string" then
				Bus.shared:emit(name, payload)
			end
		end)
	end)
end

return Bus

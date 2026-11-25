--!strict
-- Configs (ReplicatedStorage.kit.Configs) — LIVE TUNING through Roblox's Experience Configs (ConfigService): a
-- system's numbers (damage, cooldowns, prices) change in a running game without a republish, with the code's own
-- values as the fallback (Studio without configs, an outage, a typo'd key).
--   local Tun = Configs.bind("Combat", CombatConfig)   -- CombatConfig = { DAMAGE = 10, COOLDOWN = 0.5, ... }
--   Tun.DAMAGE                                          -- the live value for key "Combat.DAMAGE", else 10
--   Configs.changed:Connect(function(key) ... end)      -- after the live config refreshes
-- A live value must have the DEFAULT's type and be finite (Configs.coerce): a string where a number belongs, a NaN
-- or a negative cooldown typed in the dashboard falls back to the code value with one warning — never a crash.
-- Studio: ConfigService:SetTestingValue(key, value) (server) sets a value for the current session.
local Configs = {}

local snapshot: any = nil
local loading = false
local bound: { [string]: { [string]: any } } = {}
local warned: { [string]: boolean } = {}
local changedEvent: BindableEvent? = nil

-- the live value if it is usable as `default`'s type, else the default (pure; specs: kit/test/spec/loader.spec.luau)
function Configs.coerce(default: any, live: any): (any, string?)
	if live == nil then
		return default, nil
	end
	local want = typeof(default)
	if typeof(live) ~= want then
		return default, `is a {typeof(live)}, the code expects a {want}`
	end
	if want == "number" then
		if live ~= live or live == math.huge or live == -math.huge then
			return default, "is not a finite number"
		end
		if default >= 0 and live < 0 then
			return default, "is negative where the code's value is not"
		end
	end
	return live, nil
end

local function ensureSnapshot()
	if snapshot or loading then
		return
	end
	loading = true
	local ok, result = pcall(function()
		local service = game:GetService("ConfigService")
		return (service :: any):GetConfigAsync()
	end)
	loading = false
	if not ok then
		if not warned["(service)"] then
			warned["(service)"] = true
			warn("[Configs] live configs unavailable, using the code's values: " .. tostring(result))
		end
		return
	end
	snapshot = result
	pcall(function()
		snapshot.UpdateAvailable:Connect(function()
			pcall(function()
				snapshot:Refresh()
			end)
			if changedEvent then
				changedEvent:Fire("*")
			end
		end)
	end)
end

local function live(key: string): any
	ensureSnapshot()
	if not snapshot then
		return nil
	end
	local ok, value = pcall(function()
		return snapshot:GetValue(key)
	end)
	return if ok then value else nil
end

function Configs.get(key: string, default: any): any
	local value, why = Configs.coerce(default, live(key))
	if why and not warned[key] then
		warned[key] = true
		warn(`[Configs] {key} {why} — using {tostring(default)}`)
	end
	return value
end

-- a read-through view of a system's config module: every key reads "<prefix>.<KEY>" live, the module is the default
function Configs.bind(prefix: string, defaults: { [string]: any }): { [string]: any }
	bound[prefix] = defaults
	return setmetatable({}, {
		__index = function(_, k: string)
			local d = defaults[k]
			if d == nil or type(d) == "table" or type(d) == "function" then
				return d
			end
			return Configs.get(`{prefix}.{k}`, d)
		end,
		__newindex = function()
			error("[Configs] a bound config is read-only (change the live config or the module)", 2)
		end,
	}) :: any
end

Configs.changed = (function()
	local ok, ev = pcall(function()
		return Instance.new("BindableEvent")
	end)
	if ok then
		changedEvent = ev
		return ev.Event
	end
	return nil :: any
end)()

return Configs

--!strict
-- DataRules.luau — the DURABILITY decisions of a player's saved data (pure; kit/test/spec/datarules.spec.luau).
-- LIMITATIONS_FIXES_V4 8.3 ("profile_durability: session-lock contention, BindToClose flush, schema migration,
-- anti-dupe"): the rules a store (ProfileStore - vetted, VETLOG #15, catalogued not installed - or a raw DataStore
-- UpdateAsync) applies INSIDE its transform, so they are proven here without the engine:
--   lock      one server owns a profile at a time; a lock older than its ttl is STALE and may be taken (a server that
--             crashed never released it); a live lock is never stolen - the second server waits or kicks its player
--   migrate   ordered schema steps, each applied once (data.version counts them); a step that throws stops the load
--             (never a half-migrated save written back)
--   reconcile the template's missing fields filled in (new fields reach old saves), a saved value never overwritten
--   grant     an id applied once (a trade, a purchase receipt, a reward): the ledger keeps the last N ids, a repeat is
--             refused - the classic duplication is the same grant applied by two servers or twice on a retry
local DataRules = {}

DataRules.LOCK_TTL = 1800 -- seconds a lock lives without a refresh (a server refreshes it on every autosave)
DataRules.LEDGER = 64 -- grant ids kept per profile (enough for retries; old ones fall off)

local function finite(x: unknown): boolean
	return type(x) == "number" and x == x and x ~= math.huge and x ~= -math.huge
end

-- an id a store can key on: a string of 1..max characters with no control characters (a "\0" or a 100k string is
-- someone feeding the store, never a server or a receipt - kit fuzz caught both)
local function idOk(x: unknown, max: number): boolean
	return type(x) == "string" and #x >= 1 and #x <= max and not string.find(x, "%c")
end

export type Lock = { job: string, at: number }

-- may server `job` take / keep the profile at `now`? -> (ok, why)
function DataRules.canLock(lock: unknown, job: unknown, now: unknown, ttl: unknown?): (boolean, string)
	if not idOk(job, 64) or not finite(now) then
		return false, "a lock needs a server id and a time"
	end
	local life = if finite(ttl) and (ttl :: number) > 0 then ttl :: number else DataRules.LOCK_TTL
	if type(lock) ~= "table" then
		return true, "free"
	end
	local l = lock :: any
	if type(l.job) ~= "string" or not finite(l.at) then
		return true, "free (a broken lock is no lock)"
	end
	if l.job == job then
		return true, "ours"
	end
	if (now :: number) - l.at >= life then
		return true, "stale (its server stopped refreshing it)"
	end
	return false, `held by another server for {math.floor(life - ((now :: number) - l.at))} s more`
end

-- the lock this server writes when it takes / refreshes the profile
function DataRules.lock(job: string, now: number): Lock
	return { job = job, at = now }
end

-- the lock after this server lets go (on leave, on BindToClose): released only if it is ours (a server that lost the
-- lock - a stale take by another - must not clear the new owner's)
function DataRules.release(lock: unknown, job: unknown): Lock?
	if type(lock) == "table" and (lock :: any).job == job then
		return nil
	end
	return if type(lock) == "table" then lock :: any else nil
end

-- the data migrated through `steps` (an ordered list of functions data -> data), from data.version to #steps ->
-- (data, applied count) or (nil, why). The input is never changed in place
function DataRules.migrate(data: unknown, steps: { (any) -> any }): (any, number | string)
	if type(data) ~= "table" then
		return nil, "saved data is not a table"
	end
	if type(steps) ~= "table" then
		return nil, "no migration steps (a list of functions)"
	end
	for i, s in steps do
		if type(s) ~= "function" then
			return nil, `migration {i} is not a function`
		end
	end
	local out = table.clone(data :: any)
	local v = if finite(out.version) then math.floor(out.version) else 0
	if v < 0 or v > #steps then
		return nil,
			`saved version {v} is not one this game knows (0..{#steps}): a newer server wrote it - refuse, never downgrade`
	end
	local applied = 0
	for i = v + 1, #steps do
		local ok, nextData = pcall(steps[i], out)
		if not ok or type(nextData) ~= "table" then
			return nil, `migration {i} failed: {if ok then "it returned no data" else tostring(nextData)}`
		end
		out = nextData
		out.version = i
		applied += 1
	end
	return out, applied
end

-- every field of `template` the data lacks, filled in (deep: a missing key inside a table too); saved values win ->
-- a new table (template values copied, never shared)
local MAX_DEPTH = 16 -- (saved data is never this deep; a cyclic or hostile table stops here, never overflows)

local function deepCopy(x: any, depth: number): any
	if type(x) ~= "table" then
		return x
	end
	if depth > MAX_DEPTH then
		return nil
	end
	local out = {}
	for k, v in x do
		out[k] = deepCopy(v, depth + 1)
	end
	return out
end

local function reconcileAt(data: unknown, template: unknown, depth: number): any
	local out = if type(data) == "table" then table.clone(data :: any) else {}
	if type(template) ~= "table" or depth > MAX_DEPTH then
		return out
	end
	for k, v in template :: any do
		if out[k] == nil then
			out[k] = deepCopy(v, depth + 1)
		elseif type(v) == "table" and type(out[k]) == "table" and #v == 0 then
			out[k] = reconcileAt(out[k], v, depth + 1) -- (a record, not a list: its own missing fields too)
		end
	end
	return out
end

function DataRules.reconcile(data: unknown, template: { [any]: any }): any
	return reconcileAt(data, template, 0)
end

-- apply a grant `id` once -> (ok, why, ledger): a repeat is refused; the ledger keeps the last LEDGER ids
function DataRules.grant(ledger: unknown, id: unknown): (boolean, string, { string })
	local list: { string } = {}
	if type(ledger) == "table" then
		for _, x in ledger :: any do
			if type(x) == "string" then
				table.insert(list, x)
			end
		end
	end
	if not idOk(id, 128) then
		return false, "a grant needs an id (1..128 characters, no control characters)", list
	end
	if table.find(list, id :: string) then
		return false, "already applied (a duplicate: a retry or a second server)", list
	end
	table.insert(list, id :: string)
	while #list > DataRules.LEDGER do
		table.remove(list, 1)
	end
	return true, "applied", list
end

return DataRules

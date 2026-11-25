-- RateLimit.luau — per-key token bucket (key = player.UserId). Pure: you pass the clock in, so it is testable.
--   local limit = RateLimit.new(3, 1)          -- burst of 3, refills 1 token per second
--   if not limit:take(player.UserId, os.clock()) then return end
--   Players.PlayerRemoving -> limit:forget(player.UserId)
local RateLimit = {}
RateLimit.__index = RateLimit

export type RateLimit = typeof(setmetatable(
	{} :: { capacity: number, refill: number, buckets: { [any]: { tokens: number, at: number } } },
	RateLimit
))

function RateLimit.new(capacity: number, refillPerSecond: number): RateLimit
	return setmetatable({ capacity = capacity, refill = refillPerSecond, buckets = {} }, RateLimit)
end

-- a key that cannot index a table (nil, NaN) or a clock that is not a finite number (NaN, inf) is REFUSED and leaves
-- every bucket as it was: one such call used to throw "table index is NaN" inside the remote handler, or poison its
-- bucket for good (at = NaN / inf: the bucket never refilled again)
local function finite(n: unknown): boolean
	return type(n) == "number" and n == n and n ~= math.huge and n ~= -math.huge
end

function RateLimit.take(self: RateLimit, key: any, now: number): boolean
	if key == nil or key ~= key or not finite(now) then
		return false
	end
	local bucket = self.buckets[key]
	if not bucket then
		bucket = { tokens = self.capacity, at = now }
		self.buckets[key] = bucket
	end
	local elapsed = math.max(0, now - bucket.at)
	bucket.tokens = math.min(self.capacity, bucket.tokens + elapsed * self.refill)
	bucket.at = now
	if bucket.tokens >= 1 then
		bucket.tokens -= 1
		return true
	end
	return false
end

function RateLimit.forget(self: RateLimit, key: any)
	self.buckets[key] = nil
end

return RateLimit

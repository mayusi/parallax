--!strict
-- VfxEmit (kit) — THE LOW-GRAPHICS GUARD for a sprite's continuous emission (LIMITATIONS_FIXES_V4 3.4 step 3: "Because
-- Roblox throttles continuous ParticleEmitter.Rate by 50-80% at QualityLevel <= 3, hero anime beats MUST trigger via
-- explicit Emit(N) bursts").
--
-- Before: only a swarm's onBounce threw its sparks by Emit(n); every other sprite layer with a `rate` set
-- ParticleEmitter.Rate and let the engine emit - and on a low graphics setting the engine drops most of those particles,
-- so a charge's crackle or a trail of embers thinned to almost nothing on exactly the devices the kit's own detail
-- tiers (VfxBudget) had already planned for. Now, when the client's graphics level is low or left to the engine
-- (Automatic: it drops the level on a weak device and the script cannot read what it chose), VfxStage keeps the Rate at
-- 0 and throws the same particles itself: each frame of the effect's own clock, Emit(n) of what the rate owes since the
-- last frame, the fraction carried to the next (so 26 a second over 0.37 s is 9 or 10 particles, as the Rate gives at
-- full quality). The kit's own tiers still decide how many (a Low tier's rate is already cut); the engine no longer
-- cuts it again. Pure: kit/test/spec/vfxemit.spec.luau.
local VfxEmit = {}

-- the highest graphics level the engine throttles a Rate at (QualityLevel 1..3)
VfxEmit.LOW = 3
-- the longest step one frame may owe: a hitch (a stage started inside a long frame, an avatar arriving) must not dump
-- seconds of particles in one burst
VfxEmit.MAX_STEP = 0.25

-- the client's graphics level as a number: 1..10 for QualityLevel1..10, 0 for Automatic or anything unreadable.
-- Takes the SavedQualitySetting enum item (its Value: Automatic = 0, QualityLevelN = N), a number, or nil
function VfxEmit.levelOf(saved: any): number
	local v: any = saved
	if typeof(saved) == "EnumItem" or (type(saved) == "table" and saved.Value ~= nil) then
		v = (saved :: any).Value
	end
	if type(v) ~= "number" or v ~= v or v < 1 then
		return 0
	end
	return math.clamp(math.floor(v), 1, 10)
end

-- does the guard drive a rate by Emit at this level? Low (1..3) or Automatic / unknown (0): yes. A forced answer
-- (VfxStage.play's opts.emitGuard) wins
function VfxEmit.guarded(level: number, forced: boolean?): boolean
	if forced ~= nil then
		return forced
	end
	return level <= VfxEmit.LOW
end

-- how many particles a `rate` a second owes over `dt` seconds of the effect's clock, with the fraction carried from
-- the last step -> (whole particles to Emit now, the fraction carried on). A paused clock (dt 0) owes nothing; a step
-- over MAX_STEP owes MAX_STEP's worth
function VfxEmit.step(rate: number, dt: number, carry: number): (number, number)
	if not (rate > 0) or not (dt > 0) or rate ~= rate or dt ~= dt then
		return 0, if carry == carry then carry else 0
	end
	local owed = (if carry == carry then carry else 0) + rate * math.min(dt, VfxEmit.MAX_STEP)
	local n = math.floor(owed + 1e-9)
	return n, math.max(0, owed - n)
end

return VfxEmit

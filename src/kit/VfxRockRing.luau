--!strict
-- VfxRockRing (kit) — THE CRATER ON A PART FLOOR (LIMITATIONS_FIXES_V4 3.4 step 3: "non-terrain fracture rings"; 13.3.4:
-- "non-terrain rock ring decals"). Pure: kit/test/spec/vfxrockring.spec.luau (and the browser player's copy, checked
-- there in node).
--
-- Before: a crater layer carved TERRAIN only (VfxStage builders.crater: FillBall to Air, the voxels given back). On a
-- floor of parts - most arenas, the Studio booth's own floor - it did nothing at all: the hit left no mark.
-- Now VfxStage looks at what is under the crater's point. Terrain: carved as before. A part: the ROCK RING - a decal of
-- a broken stone rim round a sunken bowl, cracks running out (the texture rock_ring: assets/textures/rock_ring.json),
-- laid flat on that part's face and tinted with ITS colour, and a ring of stone chunks of the floor's own material
-- thrown up round the rim, leaning out from the hit; the chunks sink back and the mark fades before the layer ends.
-- Stone only (no blood).
local VfxRockRing = {}

VfxRockRing.TEXTURE = "rock_ring"
-- the texture's rim sits at this share of its width from the middle (rock_ring.json: ring radius 0.32): a decal of
-- width radius / RIM puts the drawn rim on the crater's radius
VfxRockRing.RIM = 0.32
VfxRockRing.POP = 0.08 -- seconds for a chunk to burst up out of the floor
VfxRockRing.SINK = 0.25 -- the share of the life at its end over which the chunks sink back and the mark fades

-- what is under the crater's point: "terrain" (the engine's Terrain: carve it), "part" (a BasePart: the rock ring) or
-- "none" (nothing there: nothing to mark). hit: { terrain = boolean } from the stage's raycast, or nil
function VfxRockRing.ground(hit: any): string
	if type(hit) ~= "table" then
		return "none"
	end
	return if hit.terrain then "terrain" else "part"
end

-- 32-bit multiply that stays exact in doubles (the product of two 32-bit numbers is not)
local function mul32(a: number, b: number): number
	local lo = b % 65536
	local hi = (b - lo) / 65536
	return ((a * hi) % 4294967296 * 65536 + a * lo) % 4294967296
end

-- a number 0..1 from (i, k, seed): an integer hash the browser player computes alike (rockRingHash)
function VfxRockRing.hash(i: number, k: number, seed: number): number
	local x = (i * 73856093 + k * 19349663 + seed * 83492791) % 4294967296
	x = bit32.bxor(x, bit32.rshift(x, 16))
	x = mul32(x, 0x45d9f3b)
	x = bit32.bxor(x, bit32.rshift(x, 16))
	x = mul32(x, 0x45d9f3b)
	x = bit32.bxor(x, bit32.rshift(x, 16))
	return x / 4294967296
end

-- how many chunks a crater of this radius throws up (or `count`, when the layer says it): about one a stud of radius,
-- 6 to 18
function VfxRockRing.count(radius: number, count: number?): number
	if type(count) == "number" and count == count then
		return math.clamp(math.floor(count), 0, 32)
	end
	return math.clamp(math.floor(radius * 1.2 + 0.5), 6, 18)
end

export type Rock = { angle: number, distance: number, size: { number }, tilt: number, yaw: number }

-- the ring's chunks, in the crater's own frame (studs, radians): round the rim, unevenly spaced, a little in and out of
-- it, each a rough block leaning OUT from the hit by 20-45 degrees and turned its own way. The same radius and seed
-- give the same ring (the browser player draws this very plan)
function VfxRockRing.plan(radius: number, seed: number, count: number?): { Rock }
	local n = VfxRockRing.count(radius, count)
	local out: { Rock } = {}
	for i = 1, n do
		local h = function(k: number): number
			return VfxRockRing.hash(i, k, seed)
		end
		local size = radius * (0.2 + 0.18 * h(3))
		table.insert(out, {
			angle = (i - 0.5 + 0.6 * (h(1) - 0.5)) / n * 2 * math.pi,
			distance = radius * (0.92 + 0.2 * h(2)),
			size = { size * (0.8 + 0.5 * h(4)), size * (0.55 + 0.55 * h(5)), size * (0.7 + 0.5 * h(6)) },
			tilt = math.rad(20 + 25 * h(7)),
			yaw = 2 * math.pi * h(8),
		})
	end
	return out
end

-- the decal's width (studs): its drawn rim on the crater's radius
function VfxRockRing.decalWidth(radius: number): number
	return radius / VfxRockRing.RIM
end

-- how far a chunk stands up out of the floor at `t` seconds into a layer of `life` (0 = sunk, 1 = up): it bursts up over
-- POP with a small overshoot, holds, and sinks back over the last SINK of the life
function VfxRockRing.rise(t: number, life: number): number
	if t <= 0 or life <= 0 or t >= life then
		return 0
	end
	local up = math.min(1, t / VfxRockRing.POP)
	local s = 1.70158
	local u = up - 1
	local burst = 1 + (s + 1) * u * u * u + s * u * u -- ease-out-back: up a touch past 1, then back to 1
	local sinkFrom = life * (1 - VfxRockRing.SINK)
	if t <= sinkFrom then
		return burst
	end
	return burst * (1 - (t - sinkFrom) / (life - sinkFrom))
end

-- the mark's transparency at `t` (0 = drawn whole, 1 = gone): whole until the last SINK of the life, then fading out
function VfxRockRing.fade(t: number, life: number): number
	if life <= 0 or t >= life then
		return 1
	end
	local from = life * (1 - VfxRockRing.SINK)
	if t <= from then
		return 0
	end
	return (t - from) / (life - from)
end

return VfxRockRing

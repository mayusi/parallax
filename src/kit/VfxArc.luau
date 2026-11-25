--!strict
-- VfxArc (ReplicatedStorage.kit.VfxArc) — the slash ARC's geometry as pure maths, no services: VfxMesh builds the mesh
-- from it, the specs test it, and the browser player mirrors it line for line (kit/vfx/player/player.js arcPoint).
-- Arc v2 (2026-10-23, the owner: "avoid generic flat planes ... the underlying shapes must already communicate a strong
-- artistic idea"). Every new param defaults to off: a preset that sets none of them gets the old crescent exactly.
--   radius, width, arc (deg), taper, skew, vertical      the crescent (v1)
--   jag (0-0.5), jagFreq (9), seed                       torn, IRREGULAR edges in the geometry (the inner, trailing
--                                                         edge rougher than the cutting front); deterministic sines,
--                                                         so the game and the player tear it the same way
--   ridge (0-1)                                          a bowed cross-section: the band bulges out of its plane, so
--                                                         it has depth and still reads seen nearly edge-on
--   twist (deg over the arc)                             the cross-section rolls along the arc (a ribbon, not a plate)
--   strands (1-5), strandSpread (0.6)                    layered ribbons in ONE mesh: radii fanned, the outer ones
--                                                         thinner and set back in depth (an energy structure, not a card)
-- The SWEEP: point(..., tail, head) lays the whole grid over the window [tail, head] of the full arc, so a slash can
-- draw itself in along the swing (head runs ahead) and erase behind it (tail follows) - by MOVING vertices, because the
-- engine ignores an EditableMesh's vertex alpha (measured 2026-10-16). The texture stays pinned to the full arc.
local VfxArc = {}

-- the torn edge: three sines of the position along the FULL arc (not the window: the tear must not crawl as it sweeps)
local function edgeNoise(ua: number, f: number, s: number): number
	local t = ua * f * 2 * math.pi
	return 0.5 * math.sin(t + s) + 0.3 * math.sin(2.3 * t + 1.7 * s) + 0.2 * math.sin(4.1 * t + 2.9 * s)
end

-- the grid's rows across the band: 2 (inner, centre, outer) unless a ridge needs the curve sampled; always EVEN, so the
-- centre row (rows / 2) is the arc's centreline (the impact frames read it)
function VfxArc.rows(p: any): number
	return if (p.ridge or 0) ~= 0 then 6 else 2
end

function VfxArc.strands(p: any): number
	return math.clamp(math.floor(p.strands or 1), 1, 5)
end

-- one vertex: u along the window (0..1), v across the band (0 inner .. 1 outer = the cutting front), k the strand
-- (0-based), tail / head the window on the full arc (0 / 1 = all of it). Returns x, y, z and the texture's u.
function VfxArc.point(
	p: any,
	u: number,
	v: number,
	k: number,
	tail: number?,
	head: number?
): (number, number, number, number)
	local r, wd, span = p.radius or 1, p.width or 0.35, math.rad(p.arc or 160)
	local sk = math.clamp(p.skew or 0.5, 0.05, 0.95)
	local t0, t1 = tail or 0, head or 1
	local ua = t0 + (t1 - t0) * u -- where on the full arc this vertex sits
	local a = (ua - 0.5) * span
	-- the taper runs over the WINDOW: a swept piece has two points of its own (a comet stroke), the full arc the old shape
	local w = if u < sk then 0.5 * u / sk else 0.5 + 0.5 * (u - sk) / (1 - sk)
	local taper = math.max(math.sin(math.pi * w), 0) ^ (p.taper or 0.7)
	local n = VfxArc.strands(p)
	local off = k - (n - 1) / 2
	local rk = r + off * (p.strandSpread or 0.6) * wd * 0.5
	local wk = wd * (1 - 0.35 * math.abs(off) / n)
	local zk = -math.abs(off) * wd * 0.15 -- the outer strands sit behind the core one
	local vv = v - 0.5
	local jag = p.jag or 0
	if jag ~= 0 then
		local s, f = (p.seed or 1) + k * 3.1, p.jagFreq or 9
		local e = if v >= 0.5 then 0.6 * edgeNoise(ua, f, s) else edgeNoise(ua, f * 1.4, s + 5.3)
		vv *= 1 + 2 * jag * e * math.abs(2 * v - 1) -- only the edges move: the centreline stays the cut
	end
	local across = vv * wk * taper
	local bulge = (p.ridge or 0) * wk * taper * (1 - (2 * v - 1) ^ 2)
	local th = math.rad(p.twist or 0) * (ua - 0.5)
	local radial = across * math.cos(th) - bulge * math.sin(th)
	local normal = across * math.sin(th) + bulge * math.cos(th) + zk
	local rr = rk + radial
	if p.vertical and p.vertical ~= 0 then -- standing in XY, bulging +X (a slash wave flying along +X); depth on Z
		return math.cos(a) * rr, math.sin(a) * rr, normal, ua
	end
	return math.sin(a) * rr, normal, -math.cos(a) * rr, ua -- flat in XZ; depth on Y
end

return VfxArc

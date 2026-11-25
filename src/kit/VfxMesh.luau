-- VfxMesh (ReplicatedStorage.kit.VfxMesh) — effect meshes built at runtime with EditableMesh: no upload, any size,
-- UVs laid out along the shape so a texture can FLOW over it (uvScroll) — a beam shell whose light streams forward,
-- a ring whose texture spins, a wind ribbon that runs along its length.
--   local mesh = VfxMesh.build("tube", { radiusBottom = 1, radiusTop = 0.6, height = 1, segments = 32 })
--   -> { part: MeshPart, native: Vector3, scroll: (offset: Vector2) -> (), destroy: () -> () }  or nil (+ reason)
-- Shapes (unit-ish, Y up; the part's Size scales them): ring, disc, tube, cone, sphere, dome, spiral, arc, rock,
-- flame (a lobed shell round a body, feet to tip), tongue (one curved flame tongue), bolt (jagged lightning tube),
-- spikes (a crown of sharp crossed blades: an anime aura's strands; one mesh made of many strips),
-- cards (crossed vertical planes through the axis: a flipbook drawing with depth — play it with cell()),
-- corona (sharp crossed blades out of a sphere in every direction: an energy ball's spiky rim, a starburst).
-- disc / ring take `planar = 1`: the texture lies flat across the shape (a magic circle seen from above).
-- Any shape takes fadeIn / fadeOut / fadeSides: per-vertex alpha (the shell's feet and tips, a tongue's edges).
-- build(..., wobble) with wobble = { amp, freq, speed } returns a deform(age) that moves every point out from the
-- axis (a living flame). The browser player (kit/vfx/player/player.js) uses the same rules.
-- Every face is built on both sides (a runtime MeshPart cannot be made double-sided).
-- Published games: Game Settings -> Security -> "Allow Mesh & Image APIs" (the owner must be ID-verified).
-- Without it (or over the client's memory budget) build() returns nil and the effect skips the layer.
local AssetService = game:GetService("AssetService")
local VfxArc = require("./VfxArc")
local VfxBudget = require("./VfxBudget")

local VfxMesh = {}

local TAU = math.pi * 2

export type Built = {
	part: MeshPart,
	native: Vector3,
	scroll: (offset: Vector2) -> (),
	cell: (col: number, row: number, cols: number, rows: number) -> (), -- show one cell of a flipbook sheet
	deform: ((age: number) -> ())?,
	erode: ((u: number) -> ())?, -- dissolve by the life fraction (build(..., erode = { start, end, soft }))
	sweep: ((tail: number, head: number) -> ())?, -- an arc drawn over [tail, head] of itself (VfxArc): moves vertices
	destroy: () -> (),
}

type Grid = { pos: { Vector3 }, uv: { Vector2 }, cols: number, rows: number }
type UvAt = ((u: number, v: number) -> Vector2)?

-- a (cols+1) x (rows+1) grid of points, triangulated both ways
local function grid(cols: number, rows: number, at: (u: number, v: number) -> Vector3, uvAt: UvAt): Grid
	local pos, uv = {}, {}
	for j = 0, rows do
		for i = 0, cols do
			local u, v = i / cols, j / rows
			table.insert(pos, at(u, v))
			-- the image's top at v = 1, as in the browser player (three.js); Roblox's v runs DOWN the image. The player is
			-- the studio (mission 02-vfx v2): what the owner judged there is what the game draws.
			table.insert(uv, if uvAt then uvAt(u, v) else Vector2.new(u, 1 - v))
		end
	end
	return { pos = pos, uv = uv, cols = cols, rows = rows }
end

local function smoothstep(a: number, b: number, x: number): number
	local t = math.clamp((x - a) / math.max(b - a, 1e-6), 0, 1)
	return t * t * (3 - 2 * t)
end

-- per-vertex alpha from the grid's (u, v) (the player's gridAlpha)
function VfxMesh.alphaAt(p: any, u: number, v: number): number
	local a = 1
	if p.fadeIn and p.fadeIn ~= 0 then
		a *= smoothstep(0, p.fadeIn, v)
	end
	if p.fadeOut and p.fadeOut ~= 0 then
		a *= 1 - smoothstep(1 - p.fadeOut, 1, v)
	end
	if p.fadeSides and p.fadeSides ~= 0 then
		a *= math.max(math.sin(math.pi * u), 0) ^ p.fadeSides
	end
	return a
end

-- THE ENGINE'S OWN LIMIT, MEASURED (a Studio play client, 2026-11-15; the owner's limitations file, F-R04). A mesh
-- that can still GROW (every freshly created EditableMesh: the FixedSize option of an empty create is ignored) costs
-- so much of the client's editable memory that only 8 can be alive at once, whatever their size - the ninth create
-- returns nil. Until this was measured every kit mesh stayed growable for as long as it was shown: an effect of a
-- hundred mesh layers drew its first eight. A FIXED-SIZE copy of the same mesh (its vertices, UVs and colours can
-- still be moved; none can be added) costs a fraction: 358 of 200 triangles each stood at once, and its ids are the
-- growable one's. So: a mesh is grown, copied to a fixed-size one, and the growable one is destroyed at once
-- (`settled`). ONE mesh is grown at a time, and nothing is created past that gate: a mesh that is growing holds a
-- large share of the memory, so layers started in one frame, each growing its own, were refused far under what the
-- client holds (a made engine: 291 built one at a time, 89 with six growing at once, 251 with two). A build waits
-- its turn - the copy takes a frame or so. The engine refuses with nil, at the create (no place to grow in, or no
-- memory for a growable one) or at the copy (no memory): with none of the kit's own growing that is the client's
-- limit as far as the kit can tell - it cannot see a game's own growable meshes - so what it teaches (the ceiling,
-- below) is forgotten again after a while. A build whose thread died while its copy yielded would hold the turn for
-- good: a turn older than GROW_STALE seconds is taken back and its mesh destroyed.
local GROW_STALE = 5
local growingNow: { em: EditableMesh, since: number }? = nil
local engineFull = 0 -- builds the engine refused (no place to grow in, or its memory full), since the client started
local NO_PLACE = "the engine gave no place to grow a mesh in"
local ENGINE_FULL = "the engine's editable-mesh memory is full"

local function doneGrowing(em: EditableMesh)
	if growingNow and growingNow.em == em then
		growingNow = nil
	end
end

local function freshMesh(): EditableMesh
	while growingNow ~= nil do
		local g = growingNow
		if os.clock() - g.since > GROW_STALE then -- (its thread died in the copy's yield)
			growingNow = nil
			pcall(function()
				g.em:Destroy()
			end)
			break
		end
		task.wait()
	end
	local em = AssetService:CreateEditableMesh({ FixedSize = false } :: any)
	if em == nil then
		engineFull += 1
		error(NO_PLACE, 0)
	end
	growingNow = { em = em, since = os.clock() }
	return em
end

-- a grown mesh -> its fixed-size copy (the grown one destroyed). The engine answers nil when its editable memory is
-- full: the build fails as that - the grown one is NOT kept in its place (kept ones would fill the eight places to
-- grow in, and then no mesh could be built at all, even after memory came free). A copy that throws fails the build
-- too. Only where the call itself is not there (an engine without it) does the grown one stand in
local function settled(em: EditableMesh): EditableMesh
	local has, call = pcall(function()
		return (AssetService :: any).CreateEditableMeshAsync
	end)
	if not has or call == nil then
		doneGrowing(em)
		return em
	end
	local ok, fixed = pcall(function()
		return (AssetService :: any):CreateEditableMeshAsync(Content.fromObject(em), { FixedSize = true })
	end)
	doneGrowing(em)
	em:Destroy()
	if ok and fixed then
		return fixed
	end
	engineFull += 1
	error(if ok then ENGINE_FULL else `the fixed-size copy failed: {fixed}`, 0)
end

-- a grown mesh whose build failed half way: destroyed, its turn given back
local function dropped(em: EditableMesh)
	doneGrowing(em)
	em:Destroy()
end

-- a list of grids written into a growable mesh (a shape may be several separate strips: a crown of spikes). Returns
-- the flat lists every later step uses: uv ids, base uvs, vertex ids, base positions.
local function fill(
	em: EditableMesh,
	gs: { Grid },
	p: any,
	needColors: boolean?
): ({ number }, { Vector2 }, { number }, { Vector3 }, { number }, { number })
	local uvIds, uvs, verts, poss, cids, alphas = {}, {}, {}, {}, {}, {}
	local faded = (p.fadeIn or 0) ~= 0 or (p.fadeOut or 0) ~= 0 or (p.fadeSides or 0) ~= 0 or needColors == true
	for _, g in gs do
		local w = g.cols + 1
		local lv, lu, lc = {}, {}, {}
		for k, pos in g.pos do
			lv[k] = em:AddVertex(pos)
			lu[k] = em:AddUV(g.uv[k])
			if faded then
				local i, j = (k - 1) % w, (k - 1) // w
				local a = VfxMesh.alphaAt(p, i / g.cols, j / g.rows)
				lc[k] = em:AddColor(Color3.new(1, 1, 1), a)
				table.insert(cids, lc[k])
				table.insert(alphas, a)
			end
			table.insert(uvIds, lu[k])
			table.insert(uvs, g.uv[k])
			table.insert(verts, lv[k])
			table.insert(poss, pos)
		end
		for j = 0, g.rows - 1 do
			for i = 0, g.cols - 1 do
				local a, b = j * w + i + 1, j * w + i + 2
				local c, d = (j + 1) * w + i + 2, (j + 1) * w + i + 1
				for _, tri in { { a, b, c }, { a, c, d }, { a, c, b }, { a, d, c } } do
					local f = em:AddTriangle(lv[tri[1]], lv[tri[2]], lv[tri[3]])
					em:SetFaceUVs(f, { lu[tri[1]], lu[tri[2]], lu[tri[3]] })
					if faded then
						em:SetFaceColors(f, { lc[tri[1]], lc[tri[2]], lc[tri[3]] })
					end
				end
			end
		end
	end
	return uvIds, uvs, verts, poss, cids, alphas
end

-- one EditableMesh from a list of grids: grown, then settled into its fixed-size copy (see the engine's limit above)
local function make(
	gs: { Grid },
	p: any,
	needColors: boolean?
): (EditableMesh, { number }, { Vector2 }, { number }, { Vector3 }, { number }, { number })
	local em = freshMesh()
	local ok, uvIds, uvs, verts, poss, cids, alphas = pcall(fill, em, gs, p, needColors)
	if not ok then
		dropped(em)
		error(uvIds, 0)
	end
	return settled(em), uvIds, uvs, verts, poss, cids, alphas
end

-- a flame shell's radius at height v (the player's flameRadius)
local function flameRadius(p: any, u: number, v: number): number
	local base, tip, lobes, lobe = p.base or 0.55, p.tip or 0.12, p.lobes or 5, p.lobe or 0.12
	local r = base * (1 - v) + tip * v + (1 - 0.5 * (base + tip)) * math.sin(math.pi * v) ^ 0.9
	return r * (1 + lobe * math.sin(lobes * u * TAU + (p.seed or 0)) * v)
end

-- a crown of sharp blades round the axis (an anime aura's strands): the player's spikeGrids, same rule
local function spikeGrids(p: any): { Grid }
	local n = math.max(1, math.round(p.count or 24))
	local R, sp, h0, h1 = p.radius or 1.4, p.spread or 0.4, p.h0 or 3, p.h1 or 7
	local lean, W, rings, sd = p.lean or 0.5, p.width or 0.35, math.max(1, p.rings or 4), p.seed or 0
	local cross = if p.cross == nil then 1 else p.cross
	local function h(i: number): number
		local x = math.sin(i * 12.9898 + sd * 78.233) * 43758.5453
		return x - math.floor(x)
	end
	local out = {}
	for i = 0, n - 1 do
		local a = (i + h(4 * i) * 0.8) / n * TAU
		local r = R + (h(4 * i + 1) - 0.5) * 2 * sp
		local H = h0 + (h1 - h0) * h(4 * i + 2)
		local w = W * (0.7 + 0.6 * h(4 * i + 3))
		local ox, oz = math.cos(a), math.sin(a)
		local planes: { { number } } = { { -oz, ox } }
		if cross ~= 0 then
			table.insert(planes, { ox, oz })
		end
		for _, pl in planes do
			local px, pz = pl[1], pl[2]
			table.insert(
				out,
				grid(1, rings, function(u, v)
					local o = r + lean * H * v ^ 1.5
					local sw = (u - 0.5) * w * (1 - v) ^ 0.9 * math.min(1, v / 0.18 + 0.15) -- thin root, widest low, a point
					return Vector3.new(ox * o + px * sw, H * v, oz * o + pz * sw)
				end)
			)
		end
	end
	return out
end

-- crossed vertical cards through the axis (a flipbook drawing given depth): `count` planes, `width` x `height`,
-- centred; each plane carries the whole image upright (Roblox uv: v runs DOWN, so the image top is v = 0)
local function cardGrids(p: any): { Grid }
	local n, W, H = math.max(1, math.round(p.count or 3)), p.width or 1, p.height or 1
	local out = {}
	for i = 0, n - 1 do
		local a = math.pi * i / n
		local cx, cz = math.cos(a), math.sin(a)
		table.insert(
			out,
			grid(1, 1, function(u, v)
				return Vector3.new(cx * (u - 0.5) * W, (v - 0.5) * H, cz * (u - 0.5) * W)
			end, function(u, v)
				return Vector2.new(u, 1 - v)
			end)
		)
	end
	return out
end

-- a corona: sharp crossed blades pointing OUT of a sphere in every direction (the player's corona, same rule)
local function coronaGrids(p: any): { Grid }
	local n = math.max(1, math.round(p.count or 60))
	local R, l0, l1, W = p.radius or 1, p.l0 or 0.3, p.l1 or 0.8, p.width or 0.15
	local sd, rings = p.seed or 0, math.max(1, p.rings or 3)
	local function h(i: number): number
		local x = math.sin(i * 12.9898 + sd * 78.233) * 43758.5453
		return x - math.floor(x)
	end
	local out = {}
	for i = 0, n - 1 do
		local y = 1 - 2 * (i + 0.5) / n
		local r = math.sqrt(math.max(0, 1 - y * y))
		local ph = i * 2.399963 + sd
		local d = Vector3.new(math.cos(ph) * r, y, math.sin(ph) * r)
		local a = Vector3.new(d.Z, 0, -d.X)
		a = if a.Magnitude < 1e-4 then Vector3.xAxis else a.Unit
		local b = d:Cross(a)
		local L = l0 + (l1 - l0) * h(4 * i + 2)
		local w = W * (0.7 + 0.6 * h(4 * i + 3))
		for _, q in { a, b } do
			table.insert(
				out,
				grid(1, rings, function(u, v)
					return d * (R + L * v) + q * ((u - 0.5) * w * (1 - v) ^ 0.9)
				end)
			)
		end
	end
	return out
end

local SHAPES: { [string]: (p: any) -> any } = {
	spikes = spikeGrids,
	corona = coronaGrids,
	cards = cardGrids,
	-- flat annulus in XZ: u around, v inner -> outer
	ring = function(p)
		local inner, outer = p.inner or 0.8, p.outer or 1
		return grid(
			p.segments or 48,
			1,
			function(u, v)
				local r = inner + (outer - inner) * v
				return Vector3.new(math.cos(u * TAU) * r, 0, math.sin(u * TAU) * r)
			end,
			if p.planar
				then function(u, v)
					local r = (inner + (outer - inner) * v) / outer
					return Vector2.new(0.5 + 0.5 * math.cos(u * TAU) * r, 0.5 + 0.5 * math.sin(u * TAU) * r)
				end
				else nil
		)
	end,
	disc = function(p)
		return grid(
			p.segments or 48,
			p.rings or 4,
			function(u, v)
				return Vector3.new(math.cos(u * TAU) * v, 0, math.sin(u * TAU) * v)
			end,
			if p.planar
				then function(u, v)
					return Vector2.new(0.5 + 0.5 * math.cos(u * TAU) * v, 0.5 + 0.5 * math.sin(u * TAU) * v)
				end
				else nil
		)
	end,
	-- ONE PIECE of a broken slab (kit/vfx/fracture.py): a convex outline `points` [[x, z], ...] about the piece's own
	-- middle, `height` thick, as a closed prism - four rows round the outline: the bottom's middle, the bottom rim,
	-- the top rim, the top's middle. Its texture is the SLAB's, laid flat: `centre` (the piece's place in the slab)
	-- and `slab` [width, depth] give every point its place in the slab's picture, so the surface breaks with it
	piece = function(p)
		local pts = p.points or { { -0.5, -0.5 }, { 0.5, -0.5 }, { 0.5, 0.5 }, { -0.5, 0.5 } }
		local n = #pts
		local h = p.height or 0.5
		local cx, cz = if p.centre then p.centre[1] else 0, if p.centre then p.centre[2] else 0
		local sw, sd = if p.slab then p.slab[1] else 1, if p.slab then p.slab[2] else 1
		local function at(u: number, v: number): (number, number, number)
			local q = pts[(math.floor(u * n + 0.5) % n) + 1]
			local row = math.floor(v * 3 + 0.5)
			local x, z = q[1], q[2]
			if row == 0 or row == 3 then
				x, z = 0, 0
			end
			return x, if row >= 2 then h / 2 else -h / 2, z
		end
		return grid(n, 3, function(u, v)
			local x, y, z = at(u, v)
			return Vector3.new(x, y, z)
		end, function(u, v)
			local x, _, z = at(u, v)
			return Vector2.new(0.5 + (cx + x) / sw, 0.5 + (cz + z) / sd)
		end)
	end,
	-- a faceted stone: a ball cut by `cuts` random planes (`seed`, `jag` = how deep the cuts go, `flat` = y squash)
	rock = function(p)
		local sd, cuts, jag, flat = p.seed or 1, p.cuts or 9, p.jag or 0.38, p.flat or 0.72
		local spike = p.spike or 0 -- the top narrows to a point (a crystal, a shard)
		local function h(i: number): number
			local x = math.sin(i * 12.9898 + sd * 78.233) * 43758.5453
			return x - math.floor(x)
		end
		local planes = {}
		for k = 0, cuts - 1 do
			local n = Vector3.new(h(3 * k) * 2 - 1, h(3 * k + 1) * 2 - 1, h(3 * k + 2) * 2 - 1)
			n = if n.Magnitude > 1e-6 then n.Unit else Vector3.yAxis
			table.insert(planes, { n = n, d = 1 - jag * h(100 + k) })
		end
		return grid(p.segments or 12, p.rings or 8, function(u, v)
			local lat = (v - 0.5) * math.pi
			local d = Vector3.new(math.cos(u * TAU) * math.cos(lat), math.sin(lat), math.sin(u * TAU) * math.cos(lat))
			local r = 1
			for _, q in planes do
				local dn = d:Dot(q.n)
				if dn > 1e-3 then
					r = math.min(r, q.d / dn)
				end
			end
			local tp = 1 - spike * math.max(0, d.Y * r)
			return Vector3.new(d.X * r * tp, d.Y * r * flat, d.Z * r * tp)
		end)
	end,
	-- open tube along +Y from 0 to height: u around, v along (a beam shell: aim Y at the target)
	tube = function(p)
		local r0, r1, h = p.radiusBottom or 1, p.radiusTop or 1, p.height or 1
		return grid(p.segments or 32, p.rings or 8, function(u, v)
			local r = r0 + (r1 - r0) * v
			return Vector3.new(math.cos(u * TAU) * r, v * h, math.sin(u * TAU) * r)
		end)
	end,
	-- a liquid CROWN (Edgerton's coronet): a thin wall flaring from `base` to `radius` over `height`, its rim rolled
	-- outward and down into a `lip`, scalloped into `scallops` lobes where the fingers break off (the player's crown)
	crown = function(p)
		local R, b, h, lip = p.radius or 1.75, p.base or 1, p.height or 1.6, p.lip or 0.18
		local n, sc = p.scallops or 18, p.scallop or 0.12
		return grid(p.segments or 64, p.rings or 20, function(u, v)
			local r, y
			if v < 0.8 then
				local t = v / 0.8
				r, y = b + (R - b) * t ^ 1.6, h * t
			else
				local th = (v - 0.8) / 0.2 * 1.25 * math.pi
				r, y = R + lip - lip * math.cos(th), h + lip * math.sin(th)
			end
			r *= 1 + sc * math.sin(n * u * TAU) * math.max(0, (v - 0.6) / 0.4)
			return Vector3.new(math.cos(u * TAU) * r, y, math.sin(u * TAU) * r)
		end)
	end,
	cone = function(p)
		local r0, h = p.radius or 1, p.height or 1
		return grid(p.segments or 32, p.rings or 8, function(u, v)
			local r = r0 * (1 - v)
			return Vector3.new(math.cos(u * TAU) * r, v * h, math.sin(u * TAU) * r)
		end)
	end,
	-- a torus in XZ (2026-10-24): u around the ring (radius), v around the tube (tube) - a smoke ring / vortex / halo; a
	-- uvScroll along v ROLLS it round its own core (the player's torus, same rule)
	torus = function(p)
		local R, r = p.radius or 1, p.tube or 0.3
		return grid(p.segments or 48, p.rings or 16, function(u, v)
			local c = R + r * math.cos(v * TAU)
			return Vector3.new(math.cos(u * TAU) * c, r * math.sin(v * TAU), math.sin(u * TAU) * c)
		end)
	end,
	sphere = function(p)
		return grid(p.segments or 32, p.rings or 16, function(u, v)
			local lat = (v - 0.5) * math.pi
			return Vector3.new(math.cos(u * TAU) * math.cos(lat), math.sin(lat), math.sin(u * TAU) * math.cos(lat))
		end)
	end,
	dome = function(p)
		local h = p.height or 1
		return grid(p.segments or 32, p.rings or 10, function(u, v)
			local lat = v * math.pi / 2
			return Vector3.new(math.cos(u * TAU) * math.cos(lat), math.sin(lat) * h, math.sin(u * TAU) * math.cos(lat))
		end)
	end,
	-- rising helix ribbon: u along the ribbon, v across it
	spiral = function(p)
		local r, h, turns, wd = p.radius or 1, p.height or 2, p.turns or 2, p.width or 0.3
		return grid(p.segments or 96, 1, function(u, v)
			local a = u * turns * TAU
			local rr = r * (p.flare and (1 + (p.flare - 1) * u) or 1)
			return Vector3.new(math.cos(a) * rr, u * h + (v - 0.5) * wd, math.sin(a) * rr)
		end)
	end,
	-- a flame shell round a body: a lathe from the feet (y 0) to the tip (y height), lobed; u around x tiles, v up x vtiles
	flame = function(p)
		local R, h, tu, tv = p.radius or 1, p.height or 2, p.tiles or 2, p.vtiles or 1
		local tw = math.rad(p.twist or 0) -- twist: degrees the shell turns from feet to tip (a fire whirl's helix)
		return grid(p.segments or 40, p.rings or 16, function(u, v)
			local r, a = R * flameRadius(p, u, v), u * TAU + tw * v
			return Vector3.new(math.cos(a) * r, v * h, math.sin(a) * r)
		end, function(u, v)
			return Vector2.new(u * tu, -v * tv) -- Roblox's v runs DOWN the image (three.js: up): flipped, see FLIP_V
		end)
	end,
	-- one flame tongue: a curved vertical ribbon, `arc` degrees wide at the bottom, narrowing by `taper`, leaning out
	tongue = function(p)
		local R, h, span = p.radius or 1, p.height or 2, math.rad(p.arc or 40)
		local taper, lean = p.taper or 0.7, p.lean or 0
		return grid(p.segments or 8, p.rings or 12, function(u, v)
			local a = (u - 0.5) * span * (1 - taper * v)
			local r = R + lean * v * v
			return Vector3.new(math.sin(a) * r, v * h, -math.cos(a) * r)
		end, function(u, v)
			return Vector2.new(u, -v)
		end)
	end,
	-- lightning: a thin jagged tube along +Y from 0 to `length`, `kinks` random bends `amp` studs off the line, thinner
	-- at both ends; `seed` picks the bends (the player's bolt)
	bolt = function(p)
		local K = math.max(2, math.round(p.kinks or 8))
		local L, A, W, sd = p.length or 4, p.amp or 0.35, p.width or 0.06, p.seed or 0
		local function h(i: number): number
			local x = math.sin(i * 12.9898 + sd * 78.233) * 43758.5453
			return x - math.floor(x)
		end
		local pts = {}
		for j = 0, K do
			local isEnd = j == 0 or j == K
			pts[j] = Vector3.new(
				if isEnd then 0 else (h(2 * j) - 0.5) * 2 * A,
				j / K * L,
				if isEnd then 0 else (h(2 * j + 1) - 0.5) * 2 * A
			)
		end
		return grid(p.segments or 5, K * 2, function(u, v)
			local sv = math.min(v * K, K - 1e-6)
			local j = math.floor(sv)
			local c = pts[j]:Lerp(pts[j + 1], sv - j)
			local r = W * (0.35 + 0.65 * math.sin(math.pi * v) ^ 0.5)
			return c + Vector3.new(math.cos(u * TAU) * r, 0, math.sin(u * TAU) * r)
		end)
	end,
	-- a MESH SEQUENCE (kit/vfx/meshseq.py -> assets/effects/seq/<name>.json, the stage passes it in as params.data):
	-- frame 1's grid; build() replays the frames on the same vertices (a baked 3D billow / splash crown)
	seq = function(p)
		local d = p.data
		if type(d) ~= "table" or type(d.frames) ~= "table" or #d.frames == 0 then
			return grid(1, 1, function(u, v)
				return Vector3.new(u - 0.5, v - 0.5, 0) * 0.01
			end)
		end
		local f0, w = d.frames[1], d.cols + 1
		-- `strips`: the frames hold that many SEPARATE grids of cols x rows, one after another (strands of hair: no
		-- face joins two strips); the vertices keep the frames' order, so build() replays them as one list
		local strips = if type(d.strips) == "number" and d.strips > 1 then math.floor(d.strips) else 1
		local per = w * (d.rows + 1) * 3
		local out = {}
		for s = 0, strips - 1 do
			table.insert(
				out,
				grid(d.cols, d.rows, function(u, v)
					local i, j = math.round(u * d.cols), math.round(v * d.rows)
					local k = s * per + (j * w + i) * 3
					return Vector3.new(f0[k + 1], f0[k + 2], f0[k + 3])
				end)
			)
		end
		return if #out == 1 then out[1] else out
	end,
	-- the slash crescent (v2: torn edges, a bowed cross-section, twist, layered strands - VfxArc, the pure maths the
	-- player mirrors): u along the arc, v inner -> outer, tips tapered to points; `skew` moves the widest point along it
	-- (0.75 = a razor front and a fat trailing body). Several strands = several grids in one mesh.
	arc = function(p)
		local cols, rows, out = p.segments or 48, VfxArc.rows(p), {}
		for k = 0, VfxArc.strands(p) - 1 do
			table.insert(
				out,
				grid(cols, rows, function(u, v)
					local x, y, z = VfxArc.point(p, u, v, k, 0, 1)
					return Vector3.new(x, y, z)
				end)
			)
		end
		return if #out == 1 then out[1] else out
	end,
}

VfxMesh.SHAPES = SHAPES
-- shapes whose texture must stand UP (a flame): their v is negated here and in scroll(), so the image's top is the
-- shape's top and uvScroll moves it the same way as in the browser player (three.js puts the image top at v = 1).
-- Every other grid maps 1 - v (grid()); only a planar disc / ring keeps its own projection (scroll() leaves it).
local FLIP_V = { flame = true, tongue = true }

-- build a shape -> a MeshPart (anchored, no collision / query / touch / shadow). May yield.
local function buildFresh(shape: string, params: any?, wobble: { number }?, erode: { number }?): (Built?, string?)
	local maker = SHAPES[shape]
	if not maker then
		return nil, `unknown mesh shape "{shape}"`
	end
	local made = maker(params or {})
	local gs: { Grid } = if made.pos then { made } else made -- one grid, or a list of strips
	local okMesh, em, uvIds, base, vertIds, basePos, colorIds, baseAlpha = pcall(make, gs, params or {}, erode ~= nil)
	if not okMesh then
		return nil, `EditableMesh unavailable: {em}` -- published game without "Allow Mesh & Image APIs", or budget
	end
	local mesh = em :: EditableMesh
	local okPart, part = pcall(function()
		return AssetService:CreateMeshPartAsync(Content.fromObject(mesh))
	end)
	if not okPart or not part then
		mesh:Destroy()
		return nil, `CreateMeshPartAsync failed: {part}`
	end
	local mp = part :: MeshPart
	mp.Anchored = true
	mp.CanCollide = false
	mp.CanQuery = false
	mp.CanTouch = false
	mp.CastShadow = false
	mp.Massless = true
	local ids = uvIds :: { number }
	local uvs = base :: { Vector2 }
	local last = Vector2.zero
	local lastCell = -1
	local deform: ((age: number) -> ())? = nil
	if wobble then
		local pts = basePos :: { Vector3 }
		-- each point moves out from the axis by amp * h^1.5 * sin(freq*angle + speed*age + 4h) (the player's deform)
		local amp, freq, speed = wobble[1] or 0, wobble[2] or 0, wobble[3] or 0
		local ymin, ymax = math.huge, -math.huge
		for _, q in pts do
			ymin, ymax = math.min(ymin, q.Y), math.max(ymax, q.Y)
		end
		local hy = math.max(ymax - ymin, 1e-6)
		local ang, hs = {}, {}
		for k, q in pts do
			ang[k] = math.atan2(q.Z, q.X)
			hs[k] = (q.Y - ymin) / hy
		end
		local vids = vertIds :: { number }
		deform = function(age: number)
			for k, q in pts do
				local d = amp * hs[k] ^ 1.5 * math.sin(freq * ang[k] + speed * age + 4 * hs[k])
				mesh:SetPosition(vids[k], q + Vector3.new(math.cos(ang[k]) * d, 0, math.sin(ang[k]) * d))
			end
		end
	end
	if shape == "seq" and params and type(params.data) == "table" and #params.data.frames > 1 then
		-- the sequence: the vertices walk the baked frames at `fps` (lerped between them; `loop` wraps, else it holds the
		-- last frame) - the player's seqFrame, same rule
		local frames, vids = params.data.frames, vertIds :: { number }
		local n, fps, loop = #frames, params.fps or 24, params.loop == true
		local lastF = -1
		deform = function(age: number)
			local f = age * fps
			f = if loop then f % n else math.clamp(f, 0, n - 1)
			if math.abs(f - lastF) < 1e-3 then
				return
			end
			lastF = f
			local a = math.floor(f)
			local b, t = if loop then (a + 1) % n else math.min(a + 1, n - 1), f - a
			local fa, fb = frames[a + 1], frames[b + 1]
			for k, id in vids do
				local q = (k - 1) * 3
				mesh:SetPosition(
					id,
					Vector3.new(
						fa[q + 1] + (fb[q + 1] - fa[q + 1]) * t,
						fa[q + 2] + (fb[q + 2] - fa[q + 2]) * t,
						fa[q + 3] + (fb[q + 3] - fa[q + 3]) * t
					)
				)
			end
		end
	end
	local erodeFn: ((u: number) -> ())? = nil
	if erode then
		-- every vertex a smooth noise value (patches), tips and faded edges going first; the threshold sweeps 0 -> 1
		-- between erode[1] and erode[2] of the life (the player's erodeAt, same rule)
		local e0, e1, soft = erode[1] or 0.6, erode[2] or 1, erode[3] or 0.15
		local sd = 0
		for i = 1, #shape do
			sd = (sd * 31 + string.byte(shape, i)) % 997
		end
		sd *= 0.37
		local pts, cid, a0 = basePos :: { Vector3 }, colorIds :: { number }, baseAlpha :: { number }
		local nz = {}
		for k, q in pts do
			local n = 0.5
				+ 0.25 * math.sin(1.7 * q.X + 2.3 * q.Z + sd) * math.cos(1.3 * q.Y + sd * 1.7)
				+ 0.25 * math.sin(2.9 * q.Y + 1.1 * q.X - sd * 0.7)
			nz[k] = n * 0.65 + (a0[k] or 1) * 0.35
		end
		local lastTh = -1
		erodeFn = function(u: number)
			local th = math.clamp((u - e0) / math.max(e1 - e0, 1e-4), 0, 1.2) * (1 + soft)
			if math.abs(th - lastTh) < 1e-3 then
				return
			end
			lastTh = th
			for k, id in cid do
				local x = math.clamp((th - nz[k]) / math.max(soft, 1e-4), 0, 1)
				mesh:SetColorAlpha(id, (a0[k] or 1) * (1 - x * x * (3 - 2 * x)))
			end
		end
	end
	-- the SWEEP (arcs): the whole grid laid over the window [tail, head] of the full arc - the slash draws itself in and
	-- erases behind - by moving the vertices (vertex alpha is ignored in the engine) and re-pinning the texture's u to the
	-- full arc; the scroll offset already applied is kept (the player's sweepAt, same rule)
	local sweepFn: ((tail: number, head: number) -> ())? = nil
	if shape == "arc" then
		local p = params or {}
		local cols, rows, n = p.segments or 48, VfxArc.rows(p), VfxArc.strands(p)
		local vids, lastT, lastH = vertIds :: { number }, -1, -1
		sweepFn = function(tail: number, head: number)
			tail, head = math.clamp(tail, 0, 1), math.clamp(head, 0, 1)
			if head < tail then
				tail, head = head, tail
			end
			if math.abs(tail - lastT) < 1e-4 and math.abs(head - lastH) < 1e-4 then
				return
			end
			lastT, lastH = tail, head
			lastCell = -1 -- every UV was rewritten: a flipbook must lay its cell again (review: the whole sheet showed)
			local idx = 0
			for k = 0, n - 1 do
				for j = 0, rows do
					for i = 0, cols do
						idx += 1
						local x, y, z, ua = VfxArc.point(p, i / cols, j / rows, k, tail, head)
						mesh:SetPosition(vids[idx], Vector3.new(x, y, z))
						uvs[idx] = Vector2.new(ua, 1 - j / rows)
						mesh:SetUV(ids[idx], uvs[idx] + last)
					end
				end
			end
		end
	end
	return {
		part = mp,
		native = mp.Size,
		scroll = function(offset: Vector2)
			if not (params and params.planar) then -- every grid's v is flipped against the image: scroll it the same way
				offset = Vector2.new(offset.X, -offset.Y)
			end
			if (offset - last).Magnitude < 1e-4 then
				return
			end
			last = offset
			for k, id in ids do
				mesh:SetUV(id, uvs[k] + offset)
			end
		end,
		deform = deform,
		erode = erodeFn,
		sweep = sweepFn,
		cell = function(col: number, row: number, cols: number, rows: number)
			local key = col * 1000 + row
			if key == lastCell then
				return
			end
			lastCell = key
			local flipped = FLIP_V[shape] == true -- their v is negated (-v): the image row from the top = 1 + v
			for k, id in ids do
				local vy = if flipped then 1 + uvs[k].Y else uvs[k].Y
				mesh:SetUV(id, Vector2.new((col + uvs[k].X) / cols, (row + vy) / rows))
			end
		end,
		destroy = function()
			mp:Destroy()
			mesh:Destroy()
		end,
	},
		nil
end

-- the POOL: building an EditableMesh + CreateMeshPartAsync yields ~0.2-0.35 s - measured in Sample Game 2026-10-28, a
-- Helm Breaker's 0.14 s flash never showed and a cut's smear came after the cut. So a built mesh is REUSED: destroy()
-- hides it and keeps it (up to POOL_MAX per shape + params), build() hands a kept one back at once, and prewarm() builds
-- them ahead of time (Vfx.prewarm). Every state call (scroll, cell, deform, erode, sweep) sets ABSOLUTE state, so a
-- reused mesh carries nothing over; the caller's part settings are reset here (no SurfaceAppearance, no texture).
-- The client's EditableMesh MEMORY BUDGET is small and shared (Sample Game 2026-10-29: "Failed to create empty
-- EditableMesh ... memory budget limits" twice in ~50 Greatsword cuts): kept meshes hold budget too, so ALL the kept ones
-- (every shape and ribbon) share one oldest-first list capped at IDLE_MAX, and a build that fails frees the kept ones
-- and tries once more before it gives up.
-- (the caps a WARM-UP raises - Vfx.prewarmAtSpawn: an effect's meshes made ahead must still be there when it plays;
-- with 8 kept in all, 84 of the kit's 110 effects could never be warm, and were said to be: a review, 2026-11-16)
local POOL_MAX = 6
local IDLE_MAX = 8
VfxMesh.KEEP_MOST = 100 -- the most a warm-up may keep idle (the default ceiling's in-use count: the engine's memory)
local pool: { [string]: { Built } } = {}
-- every kept mesh, oldest first: free() really destroys it and takes it out of its own pool list
local idle: { { free: () -> () } } = {}

-- ADMISSION (the owner's limitations file, F-R04): the caps above bound what is KEPT; this bounds what every effect
-- together has IN USE. One count of built meshes in use (shapes and ribbons, fresh or handed out of the pool), asked
-- of VfxBudget before every hand-out: a ceiling, the last of it kept for layers marked "critical", and a limit on
-- fresh builds started a second (a build yields a quarter of a second; a mesh out of the pool costs no build and is
-- never held by the rate). A refused build returns nil and why, as a failed one does: a mesh layer then draws
-- nothing, a mesh trail its flat Trail, a fracture piece a plain block.
-- THE CEILING IS ON BY DEFAULT. Its number is measured (a Studio play client on a desktop, 2026-11-15, with the
-- fixed-size copies above): one `starblade` holds 126 kit meshes at once and the engine gave them all; with two at
-- once the engine refused its first mesh at 132 in use. A later session refused at 114: the wall MOVES with what else the client holds. So 100 in use at most, the last 10 for critical cues - under
-- the wall that client showed, so the engine is not asked for a mesh it will refuse. A phone's wall is lower and
-- was NOT measured: that is what learning is for. A client LEARNS its own: the
-- editable memory of a device is its own and cannot be read, so the first time the engine itself refuses a mesh
-- (after the kept ones were freed) what was in use then is this client's ceiling from there on - later asks over it
-- are turned away at once, the last of it stays for critical cues, and the kept meshes are not thrown away again
-- for a build that cannot succeed. Learned only from the engine's own refusal (never from a shape's fault or a
-- part that failed), counted in meshes that STAND (not the ones still being built); a later refusal with less in
-- use lowers it. It is FORGOTTEN after LEARN_HOLD seconds without a refusal: a refusal can be a passing one (a
-- game's own growable meshes held the places), and a ceiling learned then would hold the client down for the whole
-- session - the next refusal teaches again. A game may set its own budget (VfxMesh.setBudget) or none
-- (VfxMesh.setBudget(false)); setting one forgets what was learned too.
local LEARN_HOLD = 30
local DEFAULT_BUDGET = { max = 100, reserve = 10, perSecond = 1000 }
local active = 0
local recent: { number } = {} -- the clock times of the fresh builds started lately
local turned = { plain = 0, critical = 0 } -- builds refused by the budget, since the client started
local budget: { max: number, reserve: number, perSecond: number }? = DEFAULT_BUDGET
local learned: number? = nil -- the ceiling the engine showed this client (nil: it has refused nothing lately)
local learnedAt = 0
local pending = 0 -- fresh builds in flight (counted in `active`, not standing yet)

-- the mesh budget of THIS client: { max = 100, reserve = 10, perSecond = 1000 }; nil = the kit's default; false =
-- none at all. Returns what is wrong with it, or nil
function VfxMesh.setBudget(o: any): string?
	if o == nil then
		budget = DEFAULT_BUDGET
		learned = nil
		return nil
	end
	if o == false then
		budget = nil
		learned = nil
		return nil
	end
	local got, wrong = VfxBudget.budget(o)
	if got then
		budget = got
		learned = nil
	end
	return wrong
end

local function learnedNow(): number?
	if learned ~= nil and os.clock() - learnedAt > LEARN_HOLD then
		learned = nil
	end
	return learned
end

-- the budget an ask is held to now: the set one, cut to what the engine showed this client it can hold. A prewarm
-- (filling the pool ahead of time: not an effect asking) is held by none
local function heldNow(prewarm: boolean?): { max: number, reserve: number, perSecond: number }?
	if prewarm then
		return nil
	end
	return VfxBudget.ceiling(budget, learnedNow())
end

-- a fresh build failed: was it the ENGINE that refused (the one failure a ceiling is learned from)? Then the meshes
-- that stand - in use, not the ones still being built - are this client's ceiling for a while
local function learnFrom(why: any, prewarm: boolean?)
	if prewarm or type(why) ~= "string" then
		return
	end
	if string.find(why, ENGINE_FULL, 1, true) == nil and string.find(why, NO_PLACE, 1, true) == nil then
		return
	end
	local now = math.max(1, active - pending)
	local had = learnedNow()
	if had == nil or now < had then
		learned = now
	end
	learnedAt = os.clock()
end

-- what is in use now: { active, idle, refused, refusedCritical, max, reserve, learned, engineFull } (max 0 = no
-- budget; learned 0 = the engine has refused nothing; engineFull = creates the engine refused)
function VfxMesh.stats(): { [string]: number }
	local top = VfxBudget.ceiling(budget, learnedNow())
	return {
		active = active,
		idle = #idle,
		refused = turned.plain,
		refusedCritical = turned.critical,
		max = if top then top.max else 0,
		reserve = if top then top.reserve else 0,
		learned = learnedNow() or 0,
		engineFull = engineFull,
	}
end

local function refuse(critical: boolean?, why: string?): string
	if critical == true then
		turned.critical += 1
	else
		turned.plain += 1
	end
	return `over the mesh budget: {why or "no room"}`
end

local function forget(entry: { free: () -> () })
	local i = table.find(idle, entry)
	if i then
		table.remove(idle, i)
	end
end

-- destroy kept meshes, oldest first, down to `keep` of them; returns how many were freed
local function evict(keep: number): number
	local n = 0
	while #idle > keep do
		local entry = table.remove(idle, 1) :: { free: () -> () }
		entry.free()
		n += 1
	end
	return n
end

-- a fresh build; on a failure (the budget) free every kept mesh and try once more
local function withRoom<T>(attempt: () -> (T?, string?)): (T?, string?)
	local made, why = attempt()
	if made == nil and evict(0) > 0 then
		made, why = attempt()
	end
	return made, why
end

local function keyOf(v: any): string
	if type(v) ~= "table" then
		return tostring(v)
	end
	local out = {}
	for k, x in v do
		table.insert(out, tostring(k) .. "=" .. keyOf(x))
	end
	table.sort(out)
	return "{" .. table.concat(out, ",") .. "}"
end

-- the pool's key of a built mesh. A sequence's baked frames (params.data: megabytes as text) are not part of it:
-- its name and its frame count stand for them
local function poolKey(shape: string, params: any?, wobble: { number }?, erode: { number }?): string
	if shape == "seq" and type(params) == "table" and type(params.data) == "table" then
		local lean = table.clone(params)
		lean.data = if type(params.data.frames) == "table" then #params.data.frames else 0
		return shape .. keyOf(lean) .. keyOf(wobble) .. keyOf(erode)
	end
	return shape .. keyOf(params) .. keyOf(wobble) .. keyOf(erode)
end

local function clean(part: BasePart)
	part.Parent = nil
	for _, c in part:GetChildren() do
		if c:IsA("SurfaceAppearance") then
			c:Destroy()
		end
	end
	if part:IsA("MeshPart") then
		part.TextureID = ""
	end
end

local function pooled(key: string, b: Built): Built
	local destroyFresh = b.destroy
	local kept = table.clone(b)
	local entry = {
		free = function()
			local list = pool[key]
			local i = list and table.find(list, kept)
			if i then
				table.remove(list :: { Built }, i)
			end
			destroyFresh()
		end,
	}
	local released = false
	kept.destroy = function()
		if released then -- a second destroy (a layer let go at its fade, then the stage's cleanup) does nothing
			return
		end
		released = true
		active -= 1 -- (given back: in the pool or destroyed, it is not in use)
		local list = pool[key] or {}
		pool[key] = list
		if #list >= POOL_MAX or not kept.part then
			destroyFresh()
			return
		end
		clean(kept.part)
		table.insert(list, kept)
		table.insert(idle, entry)
		evict(IDLE_MAX)
	end
	local k: any = kept
	k._take = function() -- handed out again from the pool
		released = false
		forget(entry)
	end
	return kept
end

local function build(
	shape: string,
	params: any?,
	wobble: { number }?,
	erode: { number }?,
	critical: boolean?,
	prewarm: boolean?
): (Built?, string?)
	local held = heldNow(prewarm)
	local allowed, over = VfxBudget.admit(active, critical == true, held)
	if not allowed then
		return nil, refuse(critical, over)
	end
	local key = poolKey(shape, params, wobble, erode)
	local list = pool[key]
	if list and #list > 0 then -- out of the pool: no build, so the rate does not hold it
		local b = table.remove(list) :: Built
		(b :: any)._take()
		active += 1
		return b, nil
	end
	local may, fast = VfxBudget.mayStart(recent, os.clock(), critical == true, held)
	if not may then
		return nil, refuse(critical, fast)
	end
	recent = VfxBudget.started(recent, os.clock())
	active += 1 -- (counted while it is being built: the build yields, and others ask meanwhile)
	-- (a maker that THROWS - a sequence with no frames, a shape's own fault - must give its count back: it was counted
	-- before the build, and one throw left every later effect a mesh short for the rest of the session)
	pending += 1
	local ran, b, why = pcall(withRoom, function()
		return buildFresh(shape, params, wobble, erode)
	end)
	pending -= 1
	if not ran or not b then
		local reason = if ran then why else tostring(b)
		active -= 1
		learnFrom(reason, prewarm)
		return nil, reason
	end
	return pooled(key, b :: Built), nil
end

-- critical: the layer is a cue that must not be lost (it may use the budget's reserve, and is not held by the rate)
function VfxMesh.build(
	shape: string,
	params: any?,
	wobble: { number }?,
	erode: { number }?,
	critical: boolean?
): (Built?, string?)
	return build(shape, params, wobble, erode, critical, false)
end

-- build `copies` of a shape ahead of time into the pool (yields; call it in a task)
function VfxMesh.prewarm(shape: string, params: any?, wobble: { number }?, erode: { number }?, copies: number?)
	local key = poolKey(shape, params, wobble, erode)
	local have = pool[key] and #pool[key] or 0
	local made = {}
	for _ = have + 1, math.min(copies or 1, POOL_MAX) do
		-- (not an effect asking: a budget does not turn a prewarm away or count it as refused. Said per call: a flag of
		-- the module stood across the build's yield, and an effect's build started meanwhile passed as a prewarm)
		local b = build(shape, params, wobble, erode, false, true)
		if not b then
			break
		end
		table.insert(made, b)
	end
	for _, b in made do
		b.destroy() -- into the pool
	end
end

-- a RIBBON: a trail as real geometry (VfxStage's trail with "mesh": true) - two rows of `samples` points the caller
-- moves every frame, so a blade's smear is the surface it swept, never a Roblox Trail turned to face the camera. The
-- texture runs as the player draws its trail: u along the samples (0 = the oldest .. 1 = the newest), v across
-- (0 = the span's first point .. 1 = its second, the image's top at v = 1). Built spread over a +-reach box centred on
-- the origin: the part's bounds (what the engine culls by) hold the ribbon wherever its points go, and mesh space =
-- part space (the engine centres a MeshPart on its mesh's bounds).
export type Ribbon = {
	part: MeshPart,
	-- ends: { { a, b } } oldest first (world points); origin: the part's world position
	set: (ends: { { Vector3 } }, origin: Vector3) -> (),
	destroy: () -> (),
}

local function ribbonFresh(samples: number, reach: number): (Ribbon?, string?)
	local verts, uvIds = {}, {}
	-- the whole build in the pcall: with "Allow Mesh & Image APIs" off, CreateEditableMesh still returns an object and
	-- the first AddVertex throws (Sample Game, measured 2026-10-28)
	local grown: EditableMesh? = nil
	local okMesh, made = pcall(function()
		local em = freshMesh()
		grown = em
		for i = 0, samples - 1 do
			local f = i / (samples - 1)
			for side = 0, 1 do
				local corner =
					Vector3.new((f * 2 - 1) * reach, (side * 2 - 1) * reach, if i % 2 == 0 then -reach else reach)
				table.insert(verts, em:AddVertex(corner))
				table.insert(uvIds, em:AddUV(Vector2.new(f, 1 - side)))
			end
		end
		for i = 0, samples - 2 do
			local a, b, c, d = i * 2 + 1, i * 2 + 2, i * 2 + 3, i * 2 + 4 -- a / b = sample i (sides 0 / 1), c / d = sample i + 1
			for _, tri in { { a, c, b }, { b, c, d }, { a, b, c }, { b, d, c } } do -- both faces
				local face = em:AddTriangle(verts[tri[1]], verts[tri[2]], verts[tri[3]])
				em:SetFaceUVs(face, { uvIds[tri[1]], uvIds[tri[2]], uvIds[tri[3]] })
			end
		end
		grown = nil
		return settled(em)
	end)
	if grown then
		dropped(grown)
	end
	if not okMesh or not made then
		return nil, `EditableMesh unavailable: {made}`
	end
	local mesh = made :: EditableMesh
	local okPart, part = pcall(function()
		return AssetService:CreateMeshPartAsync(Content.fromObject(mesh))
	end)
	if not okPart or not part then
		mesh:Destroy()
		return nil, `CreateMeshPartAsync failed: {part}`
	end
	local mp = part :: MeshPart
	mp.Anchored = true
	mp.CanCollide, mp.CanQuery, mp.CanTouch, mp.CastShadow, mp.Massless = false, false, false, false, true
	local function set(ends: { { Vector3 } }, origin: Vector3)
		local n = #ends
		if n < 2 then
			return
		end
		for i = 0, samples - 1 do
			local k = math.min(i, n - 1) -- the slots past the newest sample fold onto it (zero-area quads)
			local f = k / (n - 1)
			local e = ends[k + 1]
			for side = 0, 1 do
				local slot = i * 2 + side + 1
				mesh:SetPosition(verts[slot], e[side + 1] - origin)
				mesh:SetUV(uvIds[slot], Vector2.new(f, 1 - side))
			end
		end
		mp.CFrame = CFrame.new(origin)
	end
	return {
		part = mp,
		set = set,
		destroy = function()
			mp:Destroy()
			mesh:Destroy()
		end,
	}, nil
end

-- ribbons pooled as the shapes are: a kept one is reused when it has at least the samples (set() folds the spare
-- slots onto the newest sample) and its box is at least as big
type KeptRibbon = { r: Ribbon, samples: number, reach: number, entry: { free: () -> () }, take: () -> () }
local ribbonPool: { KeptRibbon } = {}

local function ribbon(samples: number, reach: number, critical: boolean?, prewarm: boolean?): (Ribbon?, string?)
	local held = heldNow(prewarm)
	local allowed, over = VfxBudget.admit(active, critical == true, held)
	if not allowed then
		return nil, refuse(critical, over)
	end
	local best: number? = nil
	for i, kr in ribbonPool do -- the smallest that fits
		if kr.samples >= samples and kr.reach >= reach and (best == nil or kr.samples < ribbonPool[best].samples) then
			best = i
		end
	end
	if best then
		local kr = table.remove(ribbonPool, best) :: KeptRibbon
		kr.take()
		active += 1
		return kr.r, nil
	end
	local may, fast = VfxBudget.mayStart(recent, os.clock(), critical == true, held)
	if not may then
		return nil, refuse(critical, fast)
	end
	recent = VfxBudget.started(recent, os.clock())
	active += 1
	pending += 1
	local ran, r, why = pcall(withRoom, function()
		return ribbonFresh(samples, reach)
	end)
	pending -= 1
	if not ran or not r then
		local reason = if ran then why else tostring(r)
		active -= 1
		learnFrom(reason, prewarm)
		return nil, reason
	end
	local fresh = r :: Ribbon
	local kept = table.clone(fresh)
	local released = false
	local kr: KeptRibbon
	kr = {
		r = kept,
		samples = samples,
		reach = reach,
		entry = {
			free = function()
				local i = table.find(ribbonPool, kr)
				if i then
					table.remove(ribbonPool, i)
				end
				fresh.destroy()
			end,
		},
		take = function()
			released = false
			forget(kr.entry)
		end,
	}
	kept.destroy = function()
		if released then -- let go at its fade, then the stage's cleanup: once
			return
		end
		released = true
		active -= 1
		if #ribbonPool >= POOL_MAX * 2 then
			fresh.destroy()
			return
		end
		clean(kept.part)
		table.insert(ribbonPool, kr)
		table.insert(idle, kr.entry)
		evict(IDLE_MAX)
	end
	return kept, nil
end

function VfxMesh.ribbon(samples: number, reach: number, critical: boolean?): (Ribbon?, string?)
	return ribbon(samples, reach, critical, false)
end

-- what the pool HOLDS of one shape + params, now (a warm-up is checked against it: Vfx.isWarm)
function VfxMesh.kept(shape: string, params: any?, wobble: { number }?, erode: { number }?): number
	local list = pool[poolKey(shape, params, wobble, erode)]
	return if list then #list else 0
end

-- what the pool holds under one key (keyOf's): a warm check made every play reads this, not the key again
function VfxMesh.keptKey(key: string): number
	local list = pool[key]
	return if list then #list else 0
end

-- what the pool may keep now: (in all, of one key)
function VfxMesh.keeps(): (number, number)
	return IDLE_MAX, POOL_MAX
end

-- the pool's key of a shape + params (the same build is the same key: Vfx adds up a preset's needs by it)
function VfxMesh.keyOf(shape: string, params: any?, wobble: { number }?, erode: { number }?): string
	return poolKey(shape, params, wobble, erode)
end

-- ribbons the pool holds that can stand in for one of `samples` points and `reach` studs
function VfxMesh.keptRibbons(samples: number, reach: number): number
	local n = 0
	for _, kr in ribbonPool do
		if kr.samples >= samples and kr.reach >= reach then
			n += 1
		end
	end
	return n
end

-- raise what the pool KEEPS: `inAll` meshes in all, `perKey` of one shape + params (never lowered; KEEP_MOST at most).
-- A warm-up asks for what its presets need, so the meshes it made are not thrown away before they are used
function VfxMesh.keep(inAll: number, perKey: number)
	IDLE_MAX = math.clamp(math.max(IDLE_MAX, math.floor(inAll)), 8, VfxMesh.KEEP_MOST)
	POOL_MAX = math.clamp(math.max(POOL_MAX, math.floor(perKey)), 6, VfxMesh.KEEP_MOST)
end

-- build `copies` ribbons ahead of time into the pool (yields; call it in a task)
function VfxMesh.prewarmRibbon(samples: number, reach: number, copies: number)
	local have = 0
	for _, kr in ribbonPool do
		if kr.samples >= samples and kr.reach >= reach then
			have += 1
		end
	end
	local made = {}
	for _ = have + 1, math.min(copies, POOL_MAX * 2) do
		local r = ribbon(samples, reach, false, true)
		if not r then
			break
		end
		table.insert(made, r)
	end
	for _, r in made do
		r.destroy()
	end
end

-- a SHEET: a flat grid of cols x rows cells as real geometry, its (cols + 1) x (rows + 1) points set by the caller -
-- a mark DRAPED over uneven ground (VfxStage's decal with "wrap": the points are where rays find the ground). u runs
-- along the columns, v along the rows; both faces. Built spread over a +-reach box, as a ribbon is. Not pooled (a
-- mark is rare and long-lived); counted and held by the budget as every mesh is.
export type Sheet = {
	part: MeshPart,
	-- points: row by row (row 0 first), cols + 1 a row, world points; origin: the part's world position
	set: (points: { Vector3 }, origin: Vector3) -> (),
	destroy: () -> (),
}

-- (the two faces have points of their OWN: a point shared by a face and its back gets a normal that is the mean of
-- two opposite ones - none - and the engine lights it at random: a review leftover, stage 36)
local function sheetFresh(cols: number, rows: number, reach: number): (Sheet?, string?)
	local verts = {}
	local backs = {}
	local grown: EditableMesh? = nil
	local okMesh, made = pcall(function()
		local em = freshMesh()
		grown = em
		local uvIds = {}
		local backUvs = {}
		for j = 0, rows do
			for i = 0, cols do
				-- (spread over the box: the part's bounds, which the engine culls by, hold the sheet wherever it lies)
				local corner = Vector3.new(
					(i / cols * 2 - 1) * reach,
					if (i + j) % 2 == 0 then -reach else reach,
					(j / rows * 2 - 1) * reach
				)
				table.insert(verts, em:AddVertex(corner))
				table.insert(uvIds, em:AddUV(Vector2.new(i / cols, j / rows)))
				table.insert(backs, em:AddVertex(corner))
				table.insert(backUvs, em:AddUV(Vector2.new(i / cols, j / rows)))
			end
		end
		local w = cols + 1
		for j = 0, rows - 1 do
			for i = 0, cols - 1 do
				local a, b = j * w + i + 1, j * w + i + 2
				local c, d = (j + 1) * w + i + 2, (j + 1) * w + i + 1
				for _, tri in { { a, c, b }, { a, d, c } } do -- the face
					local face = em:AddTriangle(verts[tri[1]], verts[tri[2]], verts[tri[3]])
					em:SetFaceUVs(face, { uvIds[tri[1]], uvIds[tri[2]], uvIds[tri[3]] })
				end
				for _, tri in { { a, b, c }, { a, c, d } } do -- its back, on points of its own
					local face = em:AddTriangle(backs[tri[1]], backs[tri[2]], backs[tri[3]])
					em:SetFaceUVs(face, { backUvs[tri[1]], backUvs[tri[2]], backUvs[tri[3]] })
				end
			end
		end
		grown = nil
		return settled(em)
	end)
	if grown then
		dropped(grown)
	end
	if not okMesh or not made then
		return nil, `EditableMesh unavailable: {made}`
	end
	local mesh = made :: EditableMesh
	local okPart, part = pcall(function()
		return AssetService:CreateMeshPartAsync(Content.fromObject(mesh))
	end)
	if not okPart or not part then
		mesh:Destroy()
		return nil, `CreateMeshPartAsync failed: {part}`
	end
	local mp = part :: MeshPart
	mp.Anchored = true
	mp.CanCollide, mp.CanQuery, mp.CanTouch, mp.CastShadow, mp.Massless = false, false, false, false, true
	return {
		part = mp,
		set = function(points: { Vector3 }, origin: Vector3)
			for k, id in verts do
				local q = points[k]
				if q then
					mesh:SetPosition(id, q - origin)
					mesh:SetPosition(backs[k], q - origin)
				end
			end
			mp.CFrame = CFrame.new(origin)
		end,
		destroy = function()
			mp:Destroy()
			mesh:Destroy()
		end,
	},
		nil
end

function VfxMesh.sheet(cols: number, rows: number, reach: number, critical: boolean?): (Sheet?, string?)
	local allowed, over = VfxBudget.admit(active, critical == true, heldNow(false))
	if not allowed then
		return nil, refuse(critical, over)
	end
	active += 1
	pending += 1
	local ran, s, why = pcall(withRoom, function()
		return sheetFresh(cols, rows, reach)
	end)
	pending -= 1
	if not ran or not s then
		local reason = if ran then why else tostring(s)
		active -= 1
		learnFrom(reason, false)
		return nil, reason
	end
	local fresh = s :: Sheet
	local kept = table.clone(fresh)
	local released = false
	kept.destroy = function()
		if released then
			return
		end
		released = true
		active -= 1
		fresh.destroy()
	end
	return kept, nil
end

return VfxMesh

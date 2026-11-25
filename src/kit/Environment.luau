-- Environment (ReplicatedStorage.kit.Environment) — applies a world's lighting + terrain (from `kit world`).
--   Environment.applyAll()      every KitWorld model with a KitEnvironment attribute (the kit server script calls
--                               this at start; in Studio edit mode you may call it to look — it edits the place)
--   Environment.apply(env)      one decoded environment table
--   Environment.lighting(spec)  just lighting (a preset table or overrides) — e.g. darken the sky for a cutscene
-- Terrain "ground" is generated deterministically from its seed (same terrain on every server and every run).
local HttpService = game:GetService("HttpService")
local Lighting = game:GetService("Lighting")
local MaterialService = game:GetService("MaterialService")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local Environment = {}

local function c3(v: any, default: Color3): Color3
	if type(v) == "table" then
		return Color3.fromRGB(v[1], v[2], v[3])
	end
	return default
end

local function child(parent: Instance, class: string, name: string): any
	local found = parent:FindFirstChild(name)
	if found and found.ClassName == class then
		return found
	end
	-- only one Atmosphere / Clouds / Sky counts: replace any other
	if class == "Atmosphere" or class == "Clouds" or class == "Sky" then
		local other = parent:FindFirstChildOfClass(class)
		if other then
			other:Destroy()
		end
	end
	local inst = Instance.new(class)
	inst.Name = name
	inst.Parent = parent
	return inst
end

-- THE KIT'S SKY TURNED TO THE LIGHT (SkyRules): its drawn sun over the compass side the real light comes from.
-- Called when the lighting is set and by the world's clock as the hour moves; at night the sky is left as it stands
function Environment.turnSky()
	local module = script.Parent:FindFirstChild("SkyRules")
	if not module then
		return
	end
	local rules = require(module) :: any
	local box = Lighting:FindFirstChild(rules.NAME)
	local drawn = if box then box:GetAttribute(rules.DRAWN) else nil
	if not box or type(drawn) ~= "number" then
		return
	end
	local sun = Lighting:GetSunDirection()
	local turn = rules.turn(drawn, sun.X, sun.Y, sun.Z)
	if turn then
		(box :: any).SkyboxOrientation = Vector3.new(0, turn, 0)
	end
end

function Environment.lighting(l: any)
	if l.clockTime then
		Lighting.ClockTime = l.clockTime
	end
	if l.brightness then
		Lighting.Brightness = l.brightness
	end
	if l.geographicLatitude then -- how high the sun climbs (a northern hold: a low winter sun)
		Lighting.GeographicLatitude = l.geographicLatitude
	end
	Lighting.Ambient = c3(l.ambient, Lighting.Ambient)
	Lighting.OutdoorAmbient = c3(l.outdoorAmbient, Lighting.OutdoorAmbient)
	if l.exposure then
		Lighting.ExposureCompensation = l.exposure
	end
	Lighting.EnvironmentDiffuseScale = 1
	Lighting.EnvironmentSpecularScale = 1
	Lighting.GlobalShadows = true
	pcall(function()
		(Lighting :: any).Technology = Enum.Technology.Future -- plugin-only in some versions; the project sets it too
	end)
	-- W5 (kit world light): Roblox's lighting style - "Realistic" (sharp sun shadows, full light) or "Soft" - and
	-- "prioritize lighting quality" (each set where the engine lets a script; said nowhere where it does not)
	if type(l.lightingStyle) == "string" then
		pcall(function()
			(Lighting :: any).LightingStyle = (Enum :: any).LightingStyle[l.lightingStyle]
		end)
	end
	if l.prioritizeQuality ~= nil then
		pcall(function()
			(Lighting :: any).PrioritizeLightingQuality = l.prioritizeQuality == true
		end)
	end
	local a = l.atmosphere
	if a then
		local atm = child(Lighting, "Atmosphere", "KitAtmosphere")
		atm.Density = a.density or atm.Density
		atm.Offset = a.offset or atm.Offset
		atm.Color = c3(a.color, atm.Color)
		atm.Decay = c3(a.decay, atm.Decay)
		atm.Glare = a.glare or atm.Glare
		atm.Haze = a.haze or atm.Haze
	end
	local b = l.bloom
	if b then
		local bloom = child(Lighting, "BloomEffect", "KitBloom")
		bloom.Intensity, bloom.Size, bloom.Threshold = b.intensity or 0.5, b.size or 24, b.threshold or 1.4
	end
	local s = l.sunRays
	if s then
		local rays = child(Lighting, "SunRaysEffect", "KitSunRays")
		rays.Intensity, rays.Spread = s.intensity or 0.1, s.spread or 0.5
	end
	local cc = l.colorCorrection
	if cc then
		local grade = child(Lighting, "ColorCorrectionEffect", "KitGrade")
		grade.Contrast = cc.contrast or 0
		grade.Saturation = cc.saturation or 0
		grade.Brightness = cc.brightness or 0
		grade.TintColor = c3(cc.tint, Color3.new(1, 1, 1))
	end
	-- A SKY OF THE KIT'S OWN: six uploaded pictures (kit world sky), each on the face it was rendered for. The
	-- pictures have their own sun in them: Roblox's sun and moon are not drawn over it, and the whole sky is
	-- turned about the vertical so that the picture's sun stands over the place the light really comes from
	-- (Roblox's sun, moon and stars are not drawn: a night world needs a sky rendered for the night)
	local sky = l.sky
	local SkyRules = script.Parent:FindFirstChild("SkyRules")
	if sky and sky.faces and SkyRules then
		local rules = require(SkyRules) :: any
		local box = child(Lighting, "Sky", rules.NAME)
		for face, id in sky.faces do
			(box :: any)[face] = id
		end
		box.CelestialBodiesShown = false
		box.StarCount = 0
		local drawn = rules.drawn(sky) -- (nil: a sky that is not turned - one with far ridges painted in it)
		box:SetAttribute(rules.DRAWN, drawn) -- (the clock turns the sky again as the light moves: WorldClock)
		if drawn == nil then
			(box :: any).SkyboxOrientation = Vector3.zero -- (as rendered, whatever an earlier sky was turned to)
		end
		Environment.turnSky()
	end
	local cl = l.clouds
	if cl then
		local clouds = child(Workspace.Terrain, "Clouds", "KitClouds")
		clouds.Cover = cl.cover or 0.5
		clouds.Density = cl.density or 0.5
		clouds.Color = c3(cl.color, Color3.new(1, 1, 1))
	end
end

local function mat(name: string?): Enum.Material
	local ok, m = pcall(function()
		return (Enum.Material :: any)[name or "Grass"]
	end)
	return if ok and m then m else Enum.Material.Grass
end

-- LAND AS A SIGNED DISTANCE (an "sdf" op: SdfRules): every 4-stud cell of the op's box is read, changed and written
-- back - a cell inside what the op makes is filled with its material, a cell inside its cutting shapes is emptied of
-- what was there (a cave under the heightmap's land), the surface runs through the cells between. In tiles of 64
-- studs so that each read and write stays small.
local function sdfLand(terrain: Terrain, spec: any)
	-- (a project whose kit runtime is older than this op has no SdfRules: said, not waited for for ever)
	local module = script.Parent:FindFirstChild("SdfRules")
	if not module then
		warn('[kit] Environment: an "sdf" terrain op needs the kit runtime\'s SdfRules module - run: lune run kit sync')
		return
	end
	local SdfRules = require(module) :: any
	local slice = os.clock()
	local lo, hi = SdfRules.bounds(spec)
	local material = mat(spec.material)
	local function snap(v: number, up: boolean): number
		return (if up then math.ceil(v / 4) else math.floor(v / 4)) * 4
	end
	local x0, y0, z0 = snap(lo[1], false), snap(lo[2], false), snap(lo[3], false)
	local x1, y1, z1 = snap(hi[1], true), snap(hi[2], true), snap(hi[3], true)
	local TILE = 64
	for tx = x0, x1 - 1, TILE do
		for tz = z0, z1 - 1, TILE do
			for ty = y0, y1 - 1, TILE do
				local ex, ey, ez = math.min(tx + TILE, x1), math.min(ty + TILE, y1), math.min(tz + TILE, z1)
				local region = Region3.new(Vector3.new(tx, ty, tz), Vector3.new(ex, ey, ez))
				local mats, occ = terrain:ReadVoxels(region, 4)
				local changed = false
				for ix = 1, (ex - tx) / 4 do
					for iy = 1, (ey - ty) / 4 do
						for iz = 1, (ez - tz) / 4 do
							local d, cut = SdfRules.at(spec, tx + ix * 4 - 2, ty + iy * 4 - 2, tz + iz * 4 - 2)
							local fill, clear = SdfRules.cell(d, cut)
							if fill > 0 or clear > 0 then
								local was = occ[ix][iy][iz] * (1 - clear)
								if fill > was then
									mats[ix][iy][iz] = material
									occ[ix][iy][iz] = fill
								else
									occ[ix][iy][iz] = was
									if was <= 0 then
										mats[ix][iy][iz] = Enum.Material.Air
									end
								end
								changed = true
							end
						end
					end
				end
				if changed then
					terrain:WriteVoxels(region, 4, mats, occ)
				end
				-- (a large op is a second or two of work: the place is let breathe between tiles)
				if os.clock() - slice > 0.05 then
					task.wait()
					slice = os.clock()
				end
			end
		end
	end
end

local function smooth(t: number): number
	t = math.clamp(t, 0, 1)
	return t * t * (3 - 2 * t)
end

-- the ground surface height at (x, z): fractal noise + flat pads (deterministic from the seed)
local function sampleHeight(spec: any, x: number, z: number): number
	-- a heightmap's samples (kit world terrain), bilinear — the SAME function as kit/lib/world.luau sampleHeight
	local s = spec.samples
	local fx = math.clamp((x - (spec.center[1] - spec.size[1] / 2)) / spec.size[1], 0, 1) * (s.nx - 1)
	local fz = math.clamp((z - (spec.center[3] - spec.size[2] / 2)) / spec.size[2], 0, 1) * (s.nz - 1)
	local ix, iz = math.min(math.floor(fx), s.nx - 2), math.min(math.floor(fz), s.nz - 2)
	local tx, tz = fx - ix, fz - iz
	local hs = s.heights
	local function at(a: number, b: number): number
		return hs[a * s.nz + b + 1]
	end
	return (at(ix, iz) * (1 - tx) + at(ix + 1, iz) * tx) * (1 - tz)
		+ (at(ix, iz + 1) * (1 - tx) + at(ix + 1, iz + 1) * tx) * tz
end

-- a road's bed cuts and fills the land (RoadBed.luau: the compiler's rule, the same file). A game synced before the
-- kit had beds has no such module: its land is left as it was
local roadBed: any = nil
local function bedded(spec: any, x: number, z: number, h: number): number
	if spec.beds == nil then
		return h
	end
	if roadBed == nil then
		local module = script.Parent:FindFirstChild("RoadBed")
		roadBed = if module then require(module) else false
		if roadBed == false then
			warn(
				"[kit Environment] this world's roads have beds and the kit's RoadBed module is not in the game: lune run kit sync"
			)
		end
	end
	return if roadBed then roadBed.apply(spec.beds, x, z, h) else h
end

local function groundHeight(spec: any, x: number, z: number): (number, number)
	if spec.samples and spec.samples.heights then
		local sh = sampleHeight(spec, x, z)
		local h = spec.center[2] + sh
		for _, pad in spec.flat or {} do
			local d = math.sqrt((x - pad.center[1]) ^ 2 + (z - pad.center[2]) ^ 2)
			local w = smooth((d - pad.radius) / (pad.radius * 0.6 + 8))
			h = (pad.height or spec.center[2]) * (1 - w) + h * w
		end
		return bedded(spec, x, z, h), math.clamp(sh / math.max(spec.samples.relief or 1, 1e-6), 0, 1)
	end
	local n = spec.noise or {}
	local amp, scale, seed = n.amplitude or 0, n.scale or 80, (n.seed or 1) * 0.6180339
	local f, a, total, norm = 1 / scale, 1, 0, 0
	for _ = 1, n.octaves or 3 do
		total += math.noise(x * f, z * f, seed) * a
		norm += a
		f *= 2
		a *= 0.5
	end
	local v = total / norm -- about -0.6..0.6
	local h = spec.center[2] + amp * v * 1.6
	for _, pad in spec.flat or {} do
		local d = math.sqrt((x - pad.center[1]) ^ 2 + (z - pad.center[2]) ^ 2)
		local w = smooth((d - pad.radius) / (pad.radius * 0.6 + 8))
		h = (pad.height or spec.center[2]) * (1 - w) + h * w
	end
	return bedded(spec, x, z, h), math.clamp(v / 1.2 + 0.5, 0, 1)
end

local function ground(spec: any)
	local terrain = Workspace.Terrain
	local cx, cy, cz = spec.center[1], spec.center[2], spec.center[3]
	local w, d = spec.size[1], spec.size[2]
	local amp = (spec.noise and spec.noise.amplitude) or 0
	if spec.samples and spec.samples.heights then
		local top = 0
		for _, v in spec.samples.heights do
			top = math.max(top, v)
		end
		spec.samples.relief = top
		amp = top -- (the voxel band must reach the highest sample)
	end
	local rock = if spec.rock then mat(spec.rock) else nil
	-- the painted surface (kit world terrain): one role per cell -> its material; borders dithered by a hash so
	-- the cells never show as a grid
	local splat, splatMats = nil, nil
	if spec.samples and type(spec.samples.splat) == "string" and spec.samples.palette then
		splat, splatMats = spec.samples.splat, {}
		for j, name in spec.samples.palette do
			splatMats[j] = mat(name)
		end
	end
	local function painted(x: number, z: number): Enum.Material?
		if not splat then
			return nil
		end
		local s = spec.samples
		local hx = math.sin(x * 12.9898 + z * 78.233) * 43758.5453
		local hz = math.sin(x * 39.3468 + z * 11.135) * 24634.6345
		local jx, jz = (hx - math.floor(hx) - 0.5) * 0.9, (hz - math.floor(hz) - 0.5) * 0.9
		local fx = math.clamp((x - (spec.center[1] - spec.size[1] / 2)) / spec.size[1], 0, 1) * (s.nx - 1)
		local fz = math.clamp((z - (spec.center[3] - spec.size[2] / 2)) / spec.size[2], 0, 1) * (s.nz - 1)
		local ix = math.clamp(math.round(fx + jx), 0, s.nx - 1)
		local iz = math.clamp(math.round(fz + jz), 0, s.nz - 1)
		local k = ix * s.nz + iz + 1
		local role = string.byte(splat, k)
		return if role then splatMats[role - 47] else nil -- ("0" = 48 -> role 1)
	end
	local layers = nil
	for _, l in spec.layers or {} do
		layers = layers or {}
		table.insert(layers, {
			mat = mat(l.material),
			minHeight = l.minHeight,
			maxHeight = l.maxHeight,
			minSlope = l.minSlope,
			maxSlope = l.maxSlope,
		})
	end
	local rockSlope = math.tan(math.rad(spec.rockSlope or 38))
	local depth = spec.depth or 24
	local surface, under = mat(spec.material), mat(spec.under or "Rock")
	local patches = {}
	for _, p in spec.patches or {} do
		table.insert(patches, { mat = mat(p.material), above = p.above or 0.6 })
	end
	local yMin = cy - depth - amp
	local yMax = cy + amp * 1.2 + 8
	-- 256-stud tiles: each WriteVoxels call stays small
	local tile = 256
	local x0 = cx - w / 2
	local z0 = cz - d / 2
	local tx = x0
	while tx < x0 + w do
		local tz = z0
		while tz < z0 + d do
			-- this tile's own surface first: the voxel band then runs from `depth` under ITS lowest point to just
			-- over its highest (the op's whole relief per tile wrote mostly air: ~94M voxels for a mountain ring)
			local flat = Region3.new(
				Vector3.new(tx, yMin, tz),
				Vector3.new(math.min(tx + tile, x0 + w), yMin + 4, math.min(tz + tile, z0 + d))
			):ExpandToGrid(4)
			local fsize = flat.Size / 4
			local nx, nz = math.round(fsize.X), math.round(fsize.Z)
			local fbase = flat.CFrame.Position - flat.Size / 2
			local hs, vs = table.create(nx), table.create(nx)
			local lo, hi = math.huge, -math.huge
			for ix = 1, nx do
				hs[ix], vs[ix] = table.create(nz), table.create(nz)
				for iz = 1, nz do
					local h, v = groundHeight(spec, fbase.X + (ix - 0.5) * 4, fbase.Z + (iz - 0.5) * 4)
					hs[ix][iz], vs[ix][iz] = h, v
					lo, hi = math.min(lo, h), math.max(hi, h)
				end
			end
			local region = Region3.new(
				-- (down to the op's floor when it has one: the map's edge stands on rock, not on air)
				Vector3.new(
					tx,
					if type(spec.floor) == "number"
						then math.min(spec.floor, lo - depth)
						else math.max(yMin, lo - depth),
					tz
				),
				Vector3.new(math.min(tx + tile, x0 + w), math.min(yMax, hi + 8), math.min(tz + tile, z0 + d))
			):ExpandToGrid(4)
			local size = region.Size / 4
			local ny = math.round(size.Y)
			local base = region.CFrame.Position - region.Size / 2
			local mats, occ = table.create(nx), table.create(nx)
			for ix = 1, nx do
				local mx, ox = table.create(ny), table.create(ny)
				for iy = 1, ny do
					mx[iy], ox[iy] = table.create(nz), table.create(nz)
				end
				for iz = 1, nz do
					local wx, wz = base.X + (ix - 0.5) * 4, base.Z + (iz - 0.5) * 4
					local h, v = hs[ix][iz], vs[ix][iz]
					local top = surface
					for _, p in patches do
						if v > p.above then
							top = p.mat
						end
					end
					local p = painted(wx, wz)
					if p then
						top = p
					elseif rock or layers then
						local hx = groundHeight(spec, wx + 2, wz) - groundHeight(spec, wx - 2, wz)
						local hz = groundHeight(spec, wx, wz + 2) - groundHeight(spec, wx, wz - 2)
						local grad = math.sqrt(hx * hx + hz * hz) / 4
						-- material layers by height above the op's centre and slope (later ones win)
						if layers then
							local slopeDeg = math.deg(math.atan(grad))
							local rel = h - cy
							for _, l in layers do
								if
									rel >= (l.minHeight or -math.huge)
									and rel <= (l.maxHeight or math.huge)
									and slopeDeg >= (l.minSlope or 0)
									and slopeDeg <= (l.maxSlope or 90)
								then
									top = l.mat
								end
							end
						end
						-- slopes steeper than rockSlope are rock (grass does not hold on a cliff)
						if rock and grad > rockSlope then
							top = rock
						end
					end
					for iy = 1, ny do
						local bottom = base.Y + (iy - 1) * 4
						local o = math.clamp((h - bottom) / 4, 0, 1)
						ox[iy][iz] = o
						mx[iy][iz] = if o <= 0 then Enum.Material.Air elseif h - bottom < 10 then top else under
					end
				end
				mats[ix], occ[ix] = mx, ox
			end
			terrain:WriteVoxels(region, 4, mats, occ)
			tz += tile
		end
		tx += tile
	end
end

function Environment.terrain(ops: { any }, holder: Instance?)
	local terrain = Workspace.Terrain
	-- backdrop land (far mountains) first: every ground tile writes Air above its own surface, so the playable
	-- ground, water and solids must come after it
	local ordered = {}
	for _, op in ops do
		if op.kind == "ground" and op.spec and op.spec.backdrop then
			table.insert(ordered, op)
		end
	end
	for _, op in ops do
		if not (op.kind == "ground" and op.spec and op.spec.backdrop) then
			table.insert(ordered, op)
		end
	end
	for _, op in ordered do
		local s = op.spec
		-- heightmap samples live in ModuleScripts inside the world model (kit world writes KitTerrain<i>_<k>: chunks
		-- under Roblox's ~200k-character Source cap), joined in order, then destroyed (they are for the server's
		-- start only: never replicated to players)
		if s.samples and s.samples.module and not s.samples.modules then
			s.samples.modules = { s.samples.module } -- (a world compiled before the chunks: one module)
		end
		if s.samples and s.samples.modules and not s.samples.heights then
			local heights, missing = {}, nil
			for _, name in s.samples.modules do
				local m = holder and holder:FindFirstChild(name)
				if m and m:IsA("ModuleScript") then
					local chunk = (require :: any)(m)
					table.move(chunk, 1, #chunk, #heights + 1, heights)
				else
					missing = name
					break
				end
			end
			if missing then
				warn(
					`[Environment] heightmap samples "{missing}" not found under {holder and holder:GetFullName() or "?"}`
				)
				continue
			end
			s.samples.heights = heights
			if s.samples.splatModules then
				local parts = {}
				for _, name in s.samples.splatModules do
					local pm = holder and holder:FindFirstChild(name)
					if pm and pm:IsA("ModuleScript") then
						table.insert(parts, (require :: any)(pm))
					end
				end
				s.samples.splat = if #parts == #s.samples.splatModules then table.concat(parts) else nil
			end
			-- (only in a running game: applied in Studio's edit mode, destroying them would delete them from the place)
			if RunService:IsRunning() then
				for _, list in { s.samples.modules, s.samples.splatModules or {} } do
					for _, name in list do
						local m = holder and holder:FindFirstChild(name)
						if m then
							m:Destroy()
						end
					end
				end
			end
		end
		if op.kind == "ground" then
			ground(s)
		elseif op.kind == "block" or op.kind == "water" then
			terrain:FillBlock(
				CFrame.new(s.center[1], s.center[2], s.center[3]),
				Vector3.new(s.size[1], s.size[2], s.size[3]),
				if op.kind == "water" then Enum.Material.Water else mat(s.material)
			)
		elseif op.kind == "ball" then
			terrain:FillBall(Vector3.new(s.center[1], s.center[2], s.center[3]), s.radius, mat(s.material))
		elseif op.kind == "cylinder" then
			terrain:FillCylinder(CFrame.new(s.center[1], s.center[2], s.center[3]), s.height, s.radius, mat(s.material))
		elseif op.kind == "sdf" then
			sdfLand(terrain, s)
		end
	end
end

-- worn trails (kit world: a path's "worn" material): the land under each stroke turns to that material — only the soft
-- surfaces (grass, leafy grass, mud, sand, ground); rock, stone and water stay. 4-stud boxes along the stroke.
function Environment.paint(strokes: { any })
	local terrain = Workspace.Terrain
	local soft = {
		Enum.Material.Grass,
		Enum.Material.LeafyGrass,
		Enum.Material.Mud,
		Enum.Material.Sand,
		Enum.Material.Ground,
	}
	for _, s in strokes do
		local target = mat(s.material)
		local half = (s.width or 8) / 2
		for _, p in s.points or {} do
			local region = Region3.new(
				Vector3.new(p[1] - half, p[2] - 6, p[3] - half),
				Vector3.new(p[1] + half, p[2] + 4, p[3] + half)
			):ExpandToGrid(4)
			for _, m in soft do
				if m ~= target then
					terrain:ReplaceMaterial(region, 4, m, target)
				end
			end
		end
	end
end

-- ground contact (kit world "contact"): the soft land under every rock, wall and building worn to that material, one
-- 4-stud cell per (x, y, z) triple of the flat list - nothing meets the grass with a clean seam (AAA gap W5)
function Environment.contact(c: any)
	if type(c) ~= "table" or type(c.cells) ~= "table" then
		return
	end
	local terrain = Workspace.Terrain
	local target = mat(c.material)
	local soft = { Enum.Material.Grass, Enum.Material.LeafyGrass, Enum.Material.Sand }
	local cells = c.cells
	for i = 1, #cells - 2, 3 do
		local x, y, z = cells[i], cells[i + 1], cells[i + 2]
		local region = Region3.new(Vector3.new(x - 2, y - 6, z - 2), Vector3.new(x + 2, y + 4, z + 2)):ExpandToGrid(4)
		for _, m in soft do
			if m ~= target then
				terrain:ReplaceMaterial(region, 4, m, target)
			end
		end
		if i % 600 == 1 then
			task.wait() -- (thousands of cells: never freeze the server start)
		end
	end
end

function Environment.apply(env: any, holder: Instance?)
	if env.lighting then
		Environment.lighting(env.lighting)
	end
	-- the world's palette on the terrain materials, and the water's look
	local terrain = Workspace.Terrain
	for m, c in env.terrainColors or {} do
		pcall(function()
			terrain:SetMaterialColor((Enum.Material :: any)[m], Color3.fromRGB(c[1], c[2], c[3]))
		end)
	end
	local w = env.water
	if type(w) == "table" then
		if w.color then
			terrain.WaterColor = Color3.fromRGB(w.color[1], w.color[2], w.color[3])
		end
		terrain.WaterTransparency = w.transparency or terrain.WaterTransparency
		terrain.WaterWaveSize = w.waveSize or terrain.WaterWaveSize
		terrain.WaterWaveSpeed = w.waveSpeed or terrain.WaterWaveSpeed
		terrain.WaterReflectance = w.reflectance or terrain.WaterReflectance
	end
	-- the scanned surfaces: each painted material drawn with its MaterialVariant (kit world materials -> kit upload;
	-- the variants ride in MaterialService, their maps written by Rojo — a game script cannot write them)
	for _, o in env.materialVariants or {} do
		local ok = pcall(function()
			MaterialService:SetBaseMaterialOverride((Enum.Material :: any)[o.material], o.variant)
		end)
		if not ok then
			warn(
				`[Environment] no MaterialVariant override for {o.material} -> {o.variant} (is MaterialService mapped?)`
			)
		end
	end
	if env.terrain then
		Environment.terrain(env.terrain, holder)
	end
	if env.contact then
		Environment.contact(env.contact)
	end
	if env.paint then
		Environment.paint(env.paint)
	end
	if env.decoration ~= nil then
		local ok = pcall(function() -- Roblox's animated grass blades on Grass terrain
			(terrain :: any).Decoration = env.decoration
		end)
		if not ok then
			warn(
				"[Environment] Terrain.Decoration could not be set from a script — set it on Workspace.Terrain in Studio"
			)
		end
	end
	-- the time of day and the wind run on the server (Lighting + Workspace replicate): kit WorldClock
	if (env.day or env.wind or env.weather) and RunService:IsServer() then
		(require :: any)(script.Parent:WaitForChild("WorldClock")).start(env, Environment.lighting)
	end
end

function Environment.applyAll(): number
	local count = 0
	local root = Workspace:FindFirstChild("KitWorld")
	if not root then
		return 0
	end
	for _, d in root:GetDescendants() do
		local json = d:GetAttribute("KitEnvironment")
		if type(json) == "string" then
			local ok, env = pcall(function()
				return HttpService:JSONDecode(json)
			end)
			if ok then
				-- (one bad world must not stop the others, the mesh swap or KitEnvironmentReady)
				local applied = xpcall(function()
					Environment.apply(env, d)
				end, function(why)
					warn(`[Environment] {d:GetFullName()}: {why}`)
				end)
				if applied then
					count += 1
				end
			else
				warn(`[Environment] {d:GetFullName()}: bad KitEnvironment JSON`)
			end
		end
	end
	return count
end

return Environment

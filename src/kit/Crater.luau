-- Crater (ReplicatedStorage.kit.Crater) — blast a REAL hole in the terrain. SERVER (terrain replicates).
--   Crater.blast(position, radius, { heal = 45, glow = true })  -> { center, radius }
-- What it does: scorches the ground around the impact (ragged ring: burnt ground -> basalt -> glowing lava at
-- the bottom), carves a bowl (about 0.65 x radius deep), throws up a broken rocky rim, lights the floor with a
-- fading orange glow. heal = seconds until the terrain is restored exactly (training ranges); nil = permanent.
-- Needs terrain under the impact (a world with "terrain": [{ "ground": ... }]); on plain parts it only glows.
-- Overlapping craters (src/kit/CraterRefs.luau): every 4-stud cell a crater touches is counted; a heal gives back
-- only the cells no other crater still holds, with the ground as it was before the FIRST of them (before, a heal
-- wrote back its own snapshot: the older one filled the newer bowl in, the newer one left the older bowl for good).
-- A permanent crater (no heal) holds its cells for good.
local Workspace = game:GetService("Workspace")

local CraterRefs = require("./CraterRefs")

local refs = CraterRefs.new()

local Crater = {}

export type Options = { heal: number?, glow: boolean?, rim: boolean? }

local SOFT = {
	[Enum.Material.Grass] = true,
	[Enum.Material.LeafyGrass] = true,
	[Enum.Material.Ground] = true,
	[Enum.Material.Mud] = true,
	[Enum.Material.Sand] = true,
	[Enum.Material.Snow] = true,
	[Enum.Material.Sandstone] = true,
	[Enum.Material.Limestone] = true,
	[Enum.Material.Rock] = true,
	[Enum.Material.Slate] = true,
	[Enum.Material.Pavement] = true,
	[Enum.Material.Asphalt] = true,
	[Enum.Material.Concrete] = true,
}

function Crater.blast(position: Vector3, radius: number, options: Options?)
	local opts: Options = options or {}
	local terrain = Workspace.Terrain
	local reach = radius * 1.8
	local region =
		Region3.new(position - Vector3.new(reach, reach, reach), position + Vector3.new(reach, reach * 0.6, reach))
			:ExpandToGrid(4)
	-- the cells this crater holds, by their place on the 4-stud grid (the untouched ground kept by the first holder)
	local before, beforeOcc = terrain:ReadVoxels(region, 4)
	local corner = region.CFrame.Position - region.Size / 2
	local gx, gy, gz = math.round(corner.X / 4), math.round(corner.Y / 4), math.round(corner.Z / 4)
	local cells = before.Size
	local keys, at = CraterRefs.grid(gx, gy, gz, cells.X, cells.Y, cells.Z)
	CraterRefs.take(refs, keys, function(k: string): CraterRefs.Cell
		local i = at[k]
		return { material = before[i[1]][i[2]][i[3]], occupancy = beforeOcc[i[1]][i[2]][i[3]] }
	end)
	-- 1. scorch: recolour the solid ground in rings, ragged with noise
	local mats, occ = terrain:ReadVoxels(region, 4)
	local size = mats.Size
	local base = region.CFrame.Position - region.Size / 2
	local seed = math.random() * 100
	for ix = 1, size.X do
		for iy = 1, size.Y do
			for iz = 1, size.Z do
				if occ[ix][iy][iz] > 0 and SOFT[mats[ix][iy][iz]] then
					local p = base + Vector3.new(ix - 0.5, iy - 0.5, iz - 0.5) * 4
					local flat = Vector3.new(p.X - position.X, 0, p.Z - position.Z)
					local d = flat.Magnitude / radius + math.noise(p.X / 9, p.Z / 9, seed) * 0.25
					if d < 0.55 then
						mats[ix][iy][iz] = Enum.Material.CrackedLava
					elseif d < 1.2 then
						mats[ix][iy][iz] = Enum.Material.Basalt
					elseif d < 1.75 then
						mats[ix][iy][iz] = Enum.Material.Ground
					end
				end
			end
		end
	end
	terrain:WriteVoxels(region, 4, mats, occ)
	-- 2. the bowl: a sphere of air centred a little above the ground -> depth ~0.65 r
	terrain:FillBall(position + Vector3.new(0, radius * 0.35, 0), radius, Enum.Material.Air)
	-- 3. a broken rim: rocks thrown up around the edge
	if opts.rim ~= false then
		local n = math.max(8, math.floor(radius / 2))
		for i = 1, n do
			local a = (i / n) * math.pi * 2 + math.random() * 0.4
			local r = radius * (0.92 + math.random() * 0.15)
			local p = position + Vector3.new(math.cos(a) * r, radius * 0.02, math.sin(a) * r)
			terrain:FillBall(
				p,
				radius * (0.12 + math.random() * 0.12),
				if i % 3 == 0 then Enum.Material.Slate else Enum.Material.Basalt
			)
		end
	end
	-- 4. the floor glows and cools
	local light: BasePart? = nil
	if opts.glow ~= false then
		local holder = Instance.new("Part")
		holder.Name = "KitCraterGlow"
		holder.Anchored = true
		holder.CanCollide = false
		holder.CanQuery = false
		holder.CanTouch = false
		holder.Transparency = 1
		holder.Size = Vector3.new(1, 1, 1)
		holder.Position = position - Vector3.new(0, radius * 0.45, 0)
		local glow = Instance.new("PointLight")
		glow.Color = Color3.fromRGB(255, 120, 40)
		glow.Range = math.min(60, radius * 2.2)
		glow.Brightness = 6
		glow.Shadows = true
		glow.Parent = holder
		holder.Parent = Workspace
		light = holder
		task.spawn(function()
			local t0 = os.clock()
			local cool = opts.heal or 25
			while holder.Parent and os.clock() - t0 < cool do
				local k = 1 - (os.clock() - t0) / cool
				glow.Brightness = 6 * k * k + 0.4 * math.sin(os.clock() * 7) * k -- flickering embers
				task.wait(0.05)
			end
			holder:Destroy()
		end)
	end
	if opts.heal then
		task.delay(opts.heal, function()
			-- only the cells no other crater holds go back, as they were before the first crater on them
			local back = CraterRefs.give(refs, keys)
			if next(back) ~= nil then
				local nowMats, nowOcc = terrain:ReadVoxels(region, 4)
				for k, cell in back do
					local i = at[k]
					nowMats[i[1]][i[2]][i[3]] = cell.material
					nowOcc[i[1]][i[2]][i[3]] = cell.occupancy
				end
				terrain:WriteVoxels(region, 4, nowMats, nowOcc)
			end
			if light and light.Parent then
				light:Destroy()
			end
		end)
	end
	return { center = position, radius = radius }
end

Crater._refs = refs -- (a probe: how many cells craters hold now)

return Crater

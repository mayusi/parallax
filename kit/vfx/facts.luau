--!nocheck
-- facts.luau — the four open ENGINE FACTS (mission 02-vfx 5.5), measured in Roblox Studio, not assumed:
--   1 vertex_alpha    does an EditableMesh's per-vertex alpha (SetColor alpha: VfxMesh fadeIn/fadeOut/erode) draw as
--                     transparency? (Neon and SmoothPlastic, beside a uniform Transparency 0.5 control and an opaque one)
--   2 wobble_cost     what VfxMesh's wobble deform (every vertex moved every frame) costs at 0 / 15 / 30 / 60 layers
--   3 highlight       does a Highlight outline draw round an EditableMesh MeshPart (and a plain Part), and its cost
--   4 mesh_flipbook   does VfxMesh cards' cell() (UV rewrite per frame) show the next cell of a 4x4 sheet, and its cost
-- Run by kit/vfx/facts.py (it serves this file + src/kit/VfxMesh.luau through kit/vfx/capture.py and reads the
-- grabs). Returns: run(VfxMesh, grab, sheetId) -> results table. The test stage sits at y = 400, away from the bench.
local RunService = game:GetService("RunService")
local Stats = game:GetService("Stats")

local ORIGIN = Vector3.new(0, 400, 0)

local function frameStep()
	local t0 = os.clock()
	RunService.Heartbeat:Wait()
	return os.clock() - t0
end

local function settle(s)
	local t0 = os.clock()
	while os.clock() - t0 < s do
		RunService.Heartbeat:Wait()
	end
end

local function screen(cam, p)
	local v = cam:WorldToViewportPoint(p)
	return { v.X / cam.ViewportSize.X, v.Y / cam.ViewportSize.Y }
end

return function(VfxMesh, grab, sheetId)
	local cam = workspace.CurrentCamera
	local saved = { cam.CameraType, cam.CFrame, cam.FieldOfView }
	cam.CameraType = Enum.CameraType.Scriptable
	cam.FieldOfView = 50
	cam.CFrame = CFrame.lookAt(ORIGIN + Vector3.new(0, 2, 26), ORIGIN + Vector3.new(0, 2, 0)) -- an EditableMesh part pivots at the mesh ORIGIN (a tube: its foot), not its centre
	local root = Instance.new("Folder")
	root.Name = "KitEngineFacts"
	root.Parent = workspace
	local back = Instance.new("Part")
	back.Anchored, back.Size, back.Material = true, Vector3.new(80, 50, 1), Enum.Material.SmoothPlastic
	back.Color = Color3.fromRGB(40, 40, 48)
	back.CFrame = CFrame.new(ORIGIN + Vector3.new(0, 0, -6))
	back.Parent = root
	local R = { viewport = { cam.ViewportSize.X, cam.ViewportSize.Y }, errors = {} }
	local function place(part, x, y, size)
		part.Size = size
		part.CFrame = CFrame.new(ORIGIN + Vector3.new(x, y, 0))
		part.Color = Color3.new(1, 1, 1)
		part.Parent = root
	end

	-- 1 vertex alpha: four tubes, alpha 1 at the bottom -> 0 at the top on the first two
	local cols = {}
	local specs = {
		{ "neon_vertex_alpha", "Neon", { fadeOut = 1 }, 0 },
		{ "plastic_vertex_alpha", "SmoothPlastic", { fadeOut = 1 }, 0 },
		{ "neon_transparency_half", "Neon", {}, 0.5 },
		{ "neon_opaque", "Neon", {}, 0 },
	}
	for k, s in specs do
		local p = { radiusBottom = 1, radiusTop = 1, height = 1, segments = 24 }
		for kk, vv in s[3] do
			p[kk] = vv
		end
		local built, why = VfxMesh.build("tube", p)
		if not built then
			table.insert(R.errors, `vertex_alpha {s[1]}: {why}`)
			continue
		end
		built.part.Material = Enum.Material[s[2]]
		built.part.Transparency = s[4]
		local x = -7.5 + (k - 1) * 5
		place(built.part, x, 0, Vector3.new(2.4, 7, 2.4))
		cols[s[1]] = {
			bottom = screen(cam, ORIGIN + Vector3.new(x, -3, 1.2)),
			top = screen(cam, ORIGIN + Vector3.new(x, 3, 1.2)),
		}
		cols[s[1] .. "_built"] = built
	end
	settle(0.6)
	R.vertex_alpha = { columns = {}, grab = grab("facts", 1) }
	for _, s in specs do
		R.vertex_alpha.columns[s[1]] = cols[s[1]]
		if cols[s[1] .. "_built"] then
			cols[s[1] .. "_built"].destroy()
		end
	end

	-- 3 highlight: a VfxMesh tube and a plain Part, a green outline on both
	local tube = VfxMesh.build("tube", { radiusBottom = 1, radiusTop = 1, height = 1, segments = 24 })
	local plain = Instance.new("Part")
	plain.Anchored, plain.Material = true, Enum.Material.SmoothPlastic
	if tube then
		tube.part.Material = Enum.Material.Neon
		tube.part.Color = Color3.fromRGB(180, 120, 255)
		place(tube.part, -4, 0, Vector3.new(3, 7, 3))
		tube.part.Color = Color3.fromRGB(180, 120, 255)
	end
	place(plain, 4, 0, Vector3.new(3, 7, 3))
	plain.Color = Color3.fromRGB(180, 120, 255)
	settle(0.5)
	local base = grab("facts", 2)
	local cpu0 = Stats.RenderCPUFrameTime
	local hs = {}
	for _, target in { tube and tube.part, plain } do
		if target then
			local h = Instance.new("Highlight")
			h.Adornee = target
			h.FillTransparency = 1
			h.OutlineTransparency = 0
			h.OutlineColor = Color3.fromRGB(0, 255, 0)
			h.DepthMode = Enum.HighlightDepthMode.AlwaysOnTop
			h.Parent = root
			table.insert(hs, h)
		end
	end
	settle(0.5)
	R.highlight = {
		grab_off = base,
		grab_on = grab("facts", 3),
		tube = { screen(cam, ORIGIN + Vector3.new(-5.5, 3.5, 1.5)), screen(cam, ORIGIN + Vector3.new(-2.5, -3.5, 1.5)) },
		part = { screen(cam, ORIGIN + Vector3.new(2.5, 3.5, 1.5)), screen(cam, ORIGIN + Vector3.new(5.5, -3.5, 1.5)) },
		render_cpu_s = { off = cpu0, on = Stats.RenderCPUFrameTime },
	}
	for _, h in hs do
		h:Destroy()
	end
	if tube then
		tube.destroy()
	end
	plain:Destroy()

	-- 4 mesh flipbook: VfxMesh cards with a 4x4 sheet, cell 0 then cell 6
	local cards = VfxMesh.build("cards", { count = 1 })
	if cards and sheetId then
		cards.part.TextureID = sheetId
		cards.part.Material = Enum.Material.Neon
		place(cards.part, 0, 0, Vector3.new(8, 8, 8))
		cards.cell(0, 0, 4, 4)
		local okPre = pcall(function()
			game:GetService("ContentProvider"):PreloadAsync({ cards.part })
		end)
		settle(0.8)
		local g0 = grab("facts", 4)
		local t0 = os.clock()
		cards.cell(2, 1, 4, 4)
		local cellCost = os.clock() - t0
		settle(0.4)
		R.mesh_flipbook = {
			sheet = sheetId,
			preloaded = okPre,
			grab_cell0 = g0,
			grab_cell6 = grab("facts", 5),
			box = { screen(cam, ORIGIN + Vector3.new(-4, 4, 0)), screen(cam, ORIGIN + Vector3.new(4, -4, 0)) },
			cell_call_ms = cellCost * 1000,
		}
		cards.destroy()
	else
		table.insert(R.errors, "mesh_flipbook: no cards mesh or no sheet id")
	end

	-- 2 wobble cost: N living flames, every vertex moved each frame
	R.wobble_cost = {}
	for _, n in { 0, 15, 30, 60 } do
		local flames = {}
		for i = 1, n do
			local f = VfxMesh.build("flame", {}, { 0.15, 5, 6 })
			if f then
				place(f.part, ((i - 1) % 10 - 4.5) * 2.2, ((i - 1) // 10 - 2.5) * 2.4, Vector3.new(1.6, 2.2, 1.6))
				f.part.Material = Enum.Material.Neon
				table.insert(flames, f)
			end
		end
		settle(0.3)
		local deformTotal, frameTotal, frames = 0, 0, 0
		local age = 0
		for _ = 1, 90 do
			local t0 = os.clock()
			for _, f in flames do
				f.deform(age)
			end
			deformTotal += os.clock() - t0
			local dt = frameStep()
			frameTotal += dt
			age += dt
			frames += 1
		end
		table.insert(R.wobble_cost, {
			layers = #flames,
			deform_ms_per_frame = deformTotal / frames * 1000,
			frame_ms = frameTotal / frames * 1000,
			render_cpu_ms = Stats.RenderCPUFrameTime * 1000,
		})
		for _, f in flames do
			f.destroy()
		end
	end

	root:Destroy()
	cam.CameraType, cam.CFrame, cam.FieldOfView = saved[1], saved[2], saved[3]
	return R
end

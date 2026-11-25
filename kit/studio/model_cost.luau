-- model_cost.luau - what a model COSTS while it is drawn, read from Roblox's own Stats in Studio (kit/tools/studio_model.py
-- pack writes a copy; a session runs it ONCE through the Studio tools, Edit, after load.luau, with the scratch place's
-- window maximised and in front: a window behind others is throttled to a few frames a second, and every number below
-- is then wrong - the frames counted say so).
--
-- With none, 1, then COUNTS copies of the model in view (clones of the one load.luau stood: copies share one mesh, as
-- a game's copies of one uploaded mesh do) it samples Stats.RenderCPUFrameTime and Stats.RenderGPUFrameTime for
-- SECONDS each and counts the frames. Returns one JSON line: {model, tris (one copy), samples: [{copies, cpu_ms,
-- gpu_ms, fps}], gpu_ms_per_copy (a straight line through the samples), note}. The copies are removed after.
-- NOT measured: memory - a MeshPart made from an EditableMesh and its EditableImages are not counted under
-- Stats' GraphicsMeshParts / GraphicsTexture tags (measured 2026-11-18: 50 copies, both unchanged).
local given = (... :: any) or {}
local TAG = given.tag or "{{TAG}}"
local COUNTS: { number } = given.counts or { 10, 50 }
local SECONDS = given.seconds or 3
local Run = game:GetService("RunService")
local Stats = game:GetService("Stats")

local model = workspace:FindFirstChild(TAG)
if not model then
	return `REFUSED: no {TAG} in Workspace (run its load.luau first)`
end
local origin = model:GetAttribute("KitStudioAt")
local base = if typeof(origin) == "CFrame" then origin.Position else Vector3.zero
local _, size = model:GetBoundingBox()
local step = math.max(size.X, size.Y, size.Z) * 1.3
local tris = 0
for _, p in model:GetDescendants() do
	if p:IsA("MeshPart") then
		tris += model:GetAttribute("Tris_" .. p.Name) or 0
	end
end

local cam = workspace.CurrentCamera
local made = {}

-- how many copies stand in the view: their middles inside the screen and in front of the camera
local function inView(): number
	local n = 0
	for _, m in made do
		local at = m:GetBoundingBox().Position
		local p, onScreen = cam:WorldToViewportPoint(at)
		if onScreen and p.Z > 0 then
			n += 1
		end
	end
	return n
end

local function sample(copies: number)
	local n, cpu, gpu, frames = 0, 0, 0, 0
	local conn = Run.Heartbeat:Connect(function()
		frames += 1
	end)
	local t0 = os.clock()
	while os.clock() - t0 < SECONDS do
		task.wait(0.1)
		n += 1
		cpu += Stats.RenderCPUFrameTime
		gpu += Stats.RenderGPUFrameTime
	end
	conn:Disconnect()
	local span = os.clock() - t0
	return {
		copies = copies,
		cpu_ms = math.round(cpu / n * 1e5) / 100,
		gpu_ms = math.round(gpu / n * 1e5) / 100,
		fps = math.round(frames / span),
		in_view = if copies <= 1 then copies else 1 + inView(),
	}
end

local parent = model.Parent
local samples = {}
model.Parent = nil
task.wait(0.5)
table.insert(samples, sample(0))
model.Parent = parent
task.wait(0.5)
table.insert(samples, sample(1))
local ok, err = pcall(function()
	-- the copies fill the camera's view (the shot's): ten across and five high a layer, each layer further back;
	-- every place is inside the view's frustum at its own depth (review 2026-11-18: a grid laid out in studs put half
	-- the copies outside the view, where they cost nothing)
	local near = (model:GetPivot().Position - cam.CFrame.Position).Magnitude
	local half = math.tan(math.rad(cam.FieldOfView) / 2)
	local aspect = cam.ViewportSize.X / math.max(cam.ViewportSize.Y, 1)
	-- far enough back that every copy has a cell of its own (no copy hidden behind another)
	local far = math.max(near + step, step * 10 / (1.7 * half * aspect), step * 5 / (1.5 * half))
	for _, total in COUNTS do
		while #made + 1 < total do
			local i = #made + 1
			local c = model:Clone()
			c.Name = TAG .. "_cost" .. i
			local col, row, layer = (i - 1) % 10, math.floor((i - 1) / 10) % 5, math.floor((i - 1) / 50)
			local depth = far + step * layer
			local hh = depth * half
			local x = ((col + 0.5) / 10 * 2 - 1) * 0.85 * hh * aspect
			local y = ((row + 0.5) / 5 * 2 - 1) * 0.75 * hh
			c:PivotTo(CFrame.new((cam.CFrame * CFrame.new(x, y, -depth)).Position) * model:GetPivot().Rotation)
			c.Parent = workspace
			table.insert(made, c)
		end
		task.wait(1)
		table.insert(samples, sample(total))
	end
end)
for _, c in made do
	c:Destroy()
end
if not ok then
	return `FAILED: {err}`
end
-- the GPU time a copy adds: a least-squares line through (copies, gpu_ms)
local sx, sy, sxx, sxy, n = 0, 0, 0, 0, #samples
for _, s in samples do
	sx += s.copies
	sy += s.gpu_ms
	sxx += s.copies * s.copies
	sxy += s.copies * s.gpu_ms
end
local slope = (n * sxy - sx * sy) / math.max(n * sxx - sx * sx, 1e-9)
return game:GetService("HttpService"):JSONEncode({
	model = model:GetAttribute("KitStudioModel"),
	tris = tris,
	at = { base.X, base.Y, base.Z },
	samples = samples,
	gpu_ms_per_copy = math.round(slope * 1e5) / 1e5,
	note = "memory not measured: EditableMesh / EditableImage are not counted under Stats' GraphicsMeshParts / GraphicsTexture",
})

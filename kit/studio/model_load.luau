-- model_load.luau - a built model stood in ROBLOX STUDIO with NO upload (kit/tools/studio_model.py pack writes the
-- payload and a copy of this file with its settings filled in; a session runs that copy ONCE through the Studio
-- tools: execute_luau, the Edit datamodel, a kit scratch place, never saved).
--
-- Every group of the manifest becomes a MeshPart made from an EditableMesh (the triangles kit/blender/studio_pack.py
-- wrote in Roblox's axes) with a SurfaceAppearance whose maps are EditableImages (the build's own PNGs, raw RGBA),
-- set the way the game sets them (kit/lib/models.luau + src/kit/Models.luau): Size = the manifest's size_studs,
-- CFrame = its center (+ the placement below), AlphaMode Transparency where the build cut or faded, the part's own
-- Transparency raised to 0.02 where it FADED (alpha_soft), the emissive mask and its strength, its render and
-- collision fidelity. The payload comes over a local HTTP server (python -m http.server on 127.0.0.1).
--
-- Settings (pack fills them): BASE (the server's URL), NAME (the asset), TAG (the folder's name in Workspace),
-- AT (where the model's origin stands), TRANSPARENCY (nil: the game's rule; a number: every faded group gets it -
-- to compare the engine's two alpha modes side by side). Returns one line: what stood where, and the stats.
-- The same settings can be given when the file is fetched and run (plugin context has loadstring):
--   loadstring(HttpService:GetAsync(BASE .. "/load.luau", true))({tag = "...", at = CFrame.new(...), transparency = 0})
-- (every setting pack fills is inside a STRING: a formatter leaves a string's text alone)
local given = (... :: any) or {}
local function numbers(text: string): { number }
	local out = {}
	for _, x in string.split(text, ",") do
		table.insert(out, tonumber(x) :: number)
	end
	return out
end
local BASE = "{{BASE}}"
local NAME = "{{NAME}}"
local TAG = given.tag or "{{TAG}}"
local AT: CFrame = given.at or CFrame.new(table.unpack(numbers("{{AT}}")))
local TRANSPARENCY: number? = if given.transparency ~= nil then given.transparency else tonumber("{{TRANSPARENCY}}")

local Assets = game:GetService("AssetService")
local Http = game:GetService("HttpService")

local function get(file: string): string
	return Http:GetAsync(BASE .. "/" .. file, true)
end

local model = Http:JSONDecode(get("model.json"))
assert(model.asset == NAME, `model_load: the server holds {model.asset}, not {NAME}`)
local old = workspace:FindFirstChild(TAG)
if old then
	old:Destroy()
end
local folder = Instance.new("Model")
folder.Name = TAG
folder:SetAttribute("KitStudioModel", NAME)
folder:SetAttribute("KitStudioAt", AT) -- (the whole placement: shot and cost frame from it)

local said = {}
for _, g in model.groups do
	local m = Http:JSONDecode(get(g.mesh))
	local em = Assets:CreateEditableMesh()
	local vs, us, ns = {}, {}, {}
	for i, p in m.verts do
		vs[i] = em:AddVertex(Vector3.new(p[1], p[2], p[3]))
	end
	for i, uv in m.uvs do
		us[i] = em:AddUV(Vector2.new(uv[1], uv[2]))
	end
	for i, n in m.normals do
		ns[i] = em:AddNormal(Vector3.new(n[1], n[2], n[3]))
	end
	for _, t in m.tris do
		local f = em:AddTriangle(vs[t[1] + 1], vs[t[2] + 1], vs[t[3] + 1])
		em:SetFaceUVs(f, { us[t[4] + 1], us[t[5] + 1], us[t[6] + 1] })
		em:SetFaceNormals(f, { ns[t[7] + 1], ns[t[8] + 1], ns[t[9] + 1] })
	end
	local opts: { [string]: any } = {}
	if g.collision_fidelity then
		opts.CollisionFidelity = Enum.CollisionFidelity[g.collision_fidelity]
	end
	if g.render_fidelity then
		opts.RenderFidelity = Enum.RenderFidelity[g.render_fidelity]
	end
	local part = Assets:CreateMeshPartAsync(Content.fromObject(em), opts)
	part.Name = g.group
	part.Size = Vector3.new(g.size[1], g.size[2], g.size[3])
	part.CFrame = AT * CFrame.new(g.center[1], g.center[2], g.center[3])
	part.Anchored = true
	local look = Instance.new("SurfaceAppearance")
	for key, map in g.maps do
		local img = Assets:CreateEditableImage({ Size = Vector2.new(map.size[1], map.size[2]) })
		img:WritePixelsBuffer(Vector2.zero, img.Size, buffer.fromstring(get(map.file)))
		look[key .. "Content"] = Content.fromObject(img)
	end
	if g.emissive_strength then
		look.EmissiveStrength = g.emissive_strength
	end
	if g.alpha_mode == "Transparency" then
		look.AlphaMode = Enum.AlphaMode.Transparency
	end
	look.Parent = part
	local t = g.transparency or 0
	if g.alpha_soft then
		t = if TRANSPARENCY ~= nil then TRANSPARENCY else math.max(t, 0.02)
	end
	part.Transparency = t
	part.Parent = folder
	folder:SetAttribute("Tris_" .. g.group, #m.tris)
	table.insert(
		said,
		`{g.group}: {#m.tris} tris, alpha {g.alpha_mode or "none"}{if g.alpha_soft then " soft" else ""}, Transparency {t}`
	)
end
folder.Parent = workspace
return `{TAG} at {AT.Position}: ` .. table.concat(said, "; ")

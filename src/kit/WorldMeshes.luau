-- WorldMeshes.luau (kit) — a world's real meshes (trees, rocks, cliffs, house skins and facade modules made by
-- `kit world meshes`, uploaded by `kit upload`): the world compiler leaves an invisible placeholder Part named
-- "KitMesh" with attributes KitMesh, MeshId, TextureId, Collide (and KitDress on a mesh that dresses a building);
-- this turns each into its MeshPart at the placeholder's size and CFrame.
-- Why at runtime: nothing can write MeshPart.MeshId (measured, see Models.luau) — AssetService:CreateMeshPartAsync
-- once per mesh id, then clones. TextureID IS writable by scripts.
--
-- A MESH THAT IS NOT THERE (the rules: WorldMeshRules.luau; the owner's limitations list, W-R01 / W-R02):
--   * not uploaded, failed or given up, a SOLID thing stands in as its own box, seen and solid; a building whose
--     skin or facade is not whole shows its own walls and roof (the parts tagged KitBlockout) - never a hole you
--     walk through, never a wall you cannot see;
--   * a failed load is tried again (3 tries a round, 4 rounds a session), in the background; when the mesh arrives
--     it takes its stand-in's place, a building is dressed and its walls hidden again;
--   * a placeholder that was taken out of the world meanwhile is never put back by a late load.
-- KitWorld's attributes say where it stands: KitMeshesMade / Pending / Failed / Missing / Held and KitMeshesReady.
--
-- `deps` (every function takes it last, optional) stands in for the engine in the kit's own specs, which run this
-- file as it is: { root(), create(meshId, fid?), now(), wait(seconds?), spawn(fn), warn(text) }.
-- Each mesh is MADE with the collision shape and level of detail WorldMeshRules.fidelity gives its placeholder (a mesh
-- that does not collide: a Box; one that does: Roblox's Default; Automatic detail) - fixed at creation, so one
-- template per mesh id and pair of settings.
local Rules = if script
	then require(script.Parent:WaitForChild("WorldMeshRules"))
	else (require :: any)("./WorldMeshRules")

local WorldMeshes = {}

local templates: { [string]: any } = {}
local loads: { [string]: any } = {}
local inflight: { [string]: boolean } = {}
-- (which swapAll's background work is the live one: a later swapAll, or stop(), ends the one before - a flag
-- "running" left a world put in after another without any background work at all)
local generation = 0

local function engine(): any
	local AssetService = game:GetService("AssetService")
	local Workspace = game:GetService("Workspace")
	return {
		root = function()
			return Workspace:FindFirstChild("KitWorld")
		end,
		-- fid: { collision, render } (WorldMeshRules.fidelity, Roblox's enum names), asked for in the options; a mesh
		-- whose settings are refused is made without them (Roblox's defaults) rather than not at all
		create = function(meshId: string, fid: any?)
			if fid then
				local ok, part = pcall(function()
					return AssetService:CreateMeshPartAsync(Content.fromUri(meshId), {
						CollisionFidelity = (Enum.CollisionFidelity :: any)[fid.collision],
						RenderFidelity = (Enum.RenderFidelity :: any)[fid.render],
					})
				end)
				if ok and part then
					return part
				end
				-- (made without them it loads: then Roblox refused the settings, and it is said - a failed web
				-- request fails this second call too and is counted as a failure by the caller)
				local plain = AssetService:CreateMeshPartAsync(Content.fromUri(meshId))
				warn(
					`[WorldMeshes] mesh {meshId} made with Roblox's defaults: {fid.collision} / {fid.render} refused ({tostring(
						part
					)})`
				)
				return plain
			end
			return AssetService:CreateMeshPartAsync(Content.fromUri(meshId))
		end,
		now = os.clock,
		wait = task.wait,
		spawn = task.spawn,
		warn = warn,
	}
end

-- the load key of a placeholder's mesh (its id and the collision shape / detail it is made with) -> key, id, fidelity
local function keyOf(d: any): (string?, string?, any)
	local meshId = d:GetAttribute("MeshId")
	if type(meshId) ~= "string" then
		return nil, nil, nil
	end
	local collision, render = Rules.fidelity(d:GetAttribute("Collide") == true)
	return Rules.key(meshId, collision, render), meshId, { collision = collision, render = render }
end

-- where a mesh stands (by its key: id + settings), loading it when the rules say it is time: "have" | "wait" |
-- "failed" | "given up"
local function load(deps: any, key: string, meshId: string, fid: any): string
	while inflight[key] do
		deps.wait()
	end
	local state = loads[key]
	if not state then
		state = Rules.new()
		loads[key] = state
	end
	local what = Rules.attempt(state, deps.now())
	if what ~= "try" then
		return what
	end
	inflight[key] = true
	local ok, part = pcall(deps.create, meshId, fid)
	inflight[key] = nil
	if ok and part then
		templates[key] = part
		Rules.loaded(state)
		return "have"
	end
	Rules.failed(state, deps.now())
	local again = Rules.attempt(state, deps.now())
	if state.fails == 1 or again == "given up" then -- (said at the first failure and at the last, not at all twelve)
		deps.warn(
			`[WorldMeshes] mesh {meshId} failed to load ({state.fails} time(s){if again == "given up"
				then ", given up for this session"
				else ", will be tried again"}): {tostring(part)}`
		)
	end
	return if again == "given up" then "given up" else "failed"
end

-- the placeholder becomes its MeshPart (the template made for its key)
local function place(d: any, key: string)
	local m = templates[key]:Clone()
	m.Name = tostring(d:GetAttribute("KitMesh"))
	m.Anchored = true
	m.Size = d.Size
	m.CFrame = d.CFrame
	m.CanCollide = d:GetAttribute("Collide") == true
	m.CanQuery = m.CanCollide
	if d:GetAttribute("KitAudioPass") then -- (foliage lets sound through: kit Acoustics)
		m:SetAttribute("KitAudioPass", true)
	end
	m.CastShadow = true
	local tex = d:GetAttribute("TextureId")
	-- a W3 module's trim sheet: the compiler wrote its SurfaceAppearance (maps filled by Rojo, which may) under the
	-- placeholder - it moves onto the MeshPart (a script cannot fill one; it can move one)
	local look = if d.FindFirstChildOfClass then d:FindFirstChildOfClass("SurfaceAppearance") else nil
	if look then
		look.Parent = m
		m.Material = d.Material
	elseif type(tex) == "string" then
		m.TextureID = tex
	else
		m.Material = d.Material
		m.Color = d.Color
	end
	m.Parent = d.Parent
	d:Destroy()
end

-- the placeholder stands in for its mesh (WorldMeshRules.standIn)
local function standIn(d: any)
	local rule = Rules.standIn({ collide = d:GetAttribute("Collide") == true, dress = d:GetAttribute("KitDress") })
	d.Transparency = if rule.show then 0 else 1
	d.CanCollide = rule.collide
	d.CanQuery = rule.collide
	d:SetAttribute("KitStandIn", if rule.show or rule.collide then true else nil)
end

-- ONE PASS over the world: every placeholder whose mesh is there becomes it, every other one gets its stand-in.
-- -> { made, pending, failed, missing }
local function pass(deps: any, root: any): any
	-- (held: a mesh that IS there, kept back because its building can never be whole - another of its meshes was
	-- never uploaded or was given up)
	local counts = { made = 0, pending = 0, failed = 0, missing = 0, held = 0 }
	local free: { any } = {}
	local dressed: { [string]: { any } } = {}
	local keys: { string } = {}
	local blockout: { [string]: { any } } = {}
	for _, d in root:GetDescendants() do
		if d:IsA("BasePart") then
			local hides = d:GetAttribute("KitBlockout")
			if type(hides) == "string" then
				blockout[hides] = blockout[hides] or {}
				table.insert(blockout[hides], d)
			elseif d:GetAttribute("KitMesh") then
				local dress = d:GetAttribute("KitDress")
				if type(dress) == "string" and dress ~= "" then
					if not dressed[dress] then
						dressed[dress] = {}
						table.insert(keys, dress)
					end
					table.insert(dressed[dress], d)
				else
					table.insert(free, d)
				end
			end
		end
	end
	local work = 0
	local function breathe()
		work += 1
		if work % 200 == 0 then
			deps.wait() -- (big forests: never freeze the server)
		end
	end
	local function state(d: any): string
		local key, meshId, fid = keyOf(d)
		if not key then
			return "missing" -- (not uploaded yet: the compiler warned)
		end
		return load(deps, key, meshId :: string, fid)
	end
	local function count(st: string)
		if st == "missing" then
			counts.missing += 1
		elseif st == "given up" then
			counts.failed += 1
		elseif st ~= "have" then
			counts.pending += 1
		end
	end
	for _, d in free do
		local st = state(d)
		if d.Parent == nil then
			continue -- (taken out of the world while its mesh loaded: a late load puts nothing back)
		end
		if st == "have" then
			place(d, (keyOf(d)) :: string)
			counts.made += 1
		else
			standIn(d)
			count(st)
		end
		breathe()
	end
	table.sort(keys)
	for _, key in keys do
		local group = dressed[key]
		local states = {}
		for i, d in group do
			states[i] = state(d)
		end
		local alive = {}
		for i, d in group do
			if d.Parent ~= nil then
				table.insert(alive, { d = d, st = states[i] })
			end
		end
		local whole = #alive == #group and Rules.dressed(states)
		-- is any of its meshes still to be tried? (if not, and it is not whole, it never will be: settled)
		local waiting = false
		for _, st in states do
			waiting = waiting or (st ~= "have" and st ~= "missing" and st ~= "given up")
		end
		if whole then
			-- the meshes first, THEN the walls hidden: if this yields in between, a house stands in walls and
			-- modules for a moment, never in hidden walls and half its modules
			for _, a in alive do
				place(a.d, (keyOf(a.d)) :: string)
				counts.made += 1
				breathe()
			end
		end
		local walls: { any } = blockout[key] or {}
		for _, part in walls do
			if part.Parent ~= nil then
				part.Transparency = if whole then 1 else 0 -- (its own walls and roof, while its dress is not whole)
			end
		end
		if not whole then
			for _, a in alive do
				standIn(a.d)
				if a.st == "have" then
					if waiting then
						counts.pending += 1 -- (it waits with the rest of its building)
					else
						counts.held += 1
					end
				else
					count(a.st)
				end
				breathe()
			end
		end
	end
	return counts
end

local function publish(root: any, total: any)
	root:SetAttribute("KitMeshesMade", total.made)
	root:SetAttribute("KitMeshesPending", total.pending)
	root:SetAttribute("KitMeshesFailed", total.failed)
	root:SetAttribute("KitMeshesMissing", total.missing)
	root:SetAttribute("KitMeshesHeld", total.held)
	root:SetAttribute("KitMeshesReady", Rules.ready(total))
end

-- every placeholder under KitWorld -> its MeshPart, or its stand-in; then, while any mesh is still to be tried, a
-- pass again in the background. -> (made, not there now, of those never uploaded)
function WorldMeshes.swapAll(given: any?): (number, number, number)
	local deps = given or engine()
	local root = deps.root()
	if not root then
		return 0, 0, 0
	end
	generation += 1
	local mine = generation
	local total = pass(deps, root)
	publish(root, total)
	if total.pending > 0 then
		deps.spawn(function()
			while generation == mine and root.Parent ~= nil do
				deps.wait(1)
				if generation ~= mine or root.Parent == nil then
					break
				end
				local again = pass(deps, root)
				total = {
					made = total.made + again.made,
					pending = again.pending,
					failed = again.failed,
					missing = again.missing,
					held = again.held,
				}
				publish(root, total)
				if again.pending == 0 then
					break
				end
			end
		end)
	end
	return total.made, total.pending + total.failed + total.missing + total.held, total.missing
end

-- is every mesh there, or settled for good (KitWorld's KitMeshesReady says the same to any script)
function WorldMeshes.ready(given: any?): boolean
	local root = (given or engine()).root()
	return root ~= nil and root:GetAttribute("KitMeshesReady") == true
end

-- stop trying (the world is being taken down); a later swapAll starts again
function WorldMeshes.stop()
	generation += 1
end

-- (the kit's specs: a fresh session)
function WorldMeshes._reset()
	templates, loads, inflight = {}, {}, {}
	generation += 1
end

return WorldMeshes

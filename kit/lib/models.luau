-- models.luau — built 3D assets -> what the game spawns (pure: no fs, testable).
-- A game script cannot give a mesh its PBR maps (SurfaceAppearance maps need Plugin capability — measured), and
-- nothing at edit time can set MeshPart.MeshId. So each asset becomes a Rojo model (src/models/<asset>.model.json,
-- ReplicatedStorage.KitModels) holding, per mesh group: the mesh id + where it sits (attributes) and a ready
-- SurfaceAppearance (written by Rojo's plugin, which may). The runtime (src/kit/Models.luau) creates each MeshPart
-- with AssetService:CreateMeshPartAsync, clones the SurfaceAppearance onto it and welds the groups together.
local serde = require("@lune/serde")

local Models = {}

-- Roblox's own names (Enum.CollisionFidelity, Enum.RenderFidelity; src/kit/ModelRules holds the same lists)
local COLLISION = { Box = true, Hull = true, Default = true, PreciseConvexDecomposition = true }
local RENDER = { Automatic = true, Precise = true, Performance = true }
local CYCLE_MAX = 190000 -- characters of one cycle's table in the model file (Roblox holds a string value to ~200,000)
local MAPS = {
	-- manifest texture key -> SurfaceAppearance property
	color = "ColorMap",
	normal = "NormalMap",
	rough = "RoughnessMap",
	metal = "MetalnessMap",
}

local function logical(path: string): string
	return string.match(path, "([%w_]+)%.[%w]+$") or path
end

-- an id from assets/ids.json for a logical file name; maps may sit under "textures" or (older) "models"
local function lookup(ids: any, kinds: { string }, name: string): string?
	for _, kind in kinds do
		local group = ids[kind]
		if type(group) == "table" and type(group[name]) == "string" then
			return group[name]
		end
	end
	return nil
end

local function vec(v: any): any
	return { Vector3 = { v[1] or 0, v[2] or 0, v[3] or 0 } }
end

-- manifest (build/models/<asset>.manifest.json) + ids.json -> (model json, missing logical names)
function Models.compile(asset: string, manifest: any, ids: any): (any, { string })
	local missing = {}
	local children = {}
	if manifest.groups and manifest.groups.Cycles and manifest.cycles then
		error(`models: {asset} has a group named Cycles: that name is the folder its action cycles are kept in`)
	end
	-- a setting the engine does not have is a broken build, not a default: say it
	for g, entry in manifest.groups or {} do
		if entry.collision_fidelity ~= nil and not COLLISION[entry.collision_fidelity] then
			error(`models: {asset}/{g} collision_fidelity {tostring(entry.collision_fidelity)} is not one of Roblox's`)
		end
		if entry.render_fidelity ~= nil and not RENDER[entry.render_fidelity] then
			error(`models: {asset}/{g} render_fidelity {tostring(entry.render_fidelity)} is not one of Roblox's`)
		end
	end
	local groupNames = {}
	for g in manifest.groups or {} do
		table.insert(groupNames, g)
	end
	table.sort(groupNames, function(a, b)
		-- main first: it becomes the root the others weld to
		if a == "main" or b == "main" then
			return a == "main"
		end
		return a < b
	end)
	for _, g in groupNames do
		local entry = manifest.groups[g]
		local meshName = logical(entry.fbx or "")
		local meshId = lookup(ids, { "models" }, meshName)
		if not meshId then
			table.insert(missing, meshName)
		end
		local props: { [string]: any } = {}
		for key, prop in MAPS do
			local file = entry.textures and entry.textures[key]
			if file then
				local id = lookup(ids, { "textures", "models" }, logical(file))
				if id then
					props[prop] = id
				else
					table.insert(missing, logical(file))
				end
			end
		end
		local emissive = entry.textures and entry.textures.emissive
		if emissive then
			local id = lookup(ids, { "textures", "models" }, logical(emissive))
			if id then
				props.EmissiveMaskContent = id -- Rojo takes Content as a plain string (the {Content=...} form is rejected)
				props.EmissiveStrength = entry.emissiveStrength or 4
			else
				table.insert(missing, logical(emissive))
			end
		end
		-- a.cutout (the manifest's alpha_mode): the colour map's alpha CUTS the mesh - a leaf's edge, a grille's
		-- bars (a 0 / 1 alpha). With the part's own Transparency 0 the engine does not blend: seen in Studio
		-- 2026-11-18 (kit/tools/studio_model.py), a GRADED alpha came out stepped into 4 flat bands, not cut clean
		if entry.alpha_mode == "Transparency" then
			props.AlphaMode = "Transparency"
		end
		-- a.fade (the manifest's alpha_soft): the map's alpha is to be BLENDED by degrees, not cut by. With the
		-- part fully opaque the engine steps it; a hair of the part's own transparency makes it blend (SEEN in
		-- Studio 2026-11-18, the fade fixture: at 0.02 no step down the pane over 4 grey levels; card s4wc)
		local transparency = entry.transparency or 0
		if entry.alpha_soft and transparency < 0.02 then
			transparency = 0.02
		end
		local attributes: { [string]: any } = {
			MeshId = meshId or "",
			Center = vec(entry.center or { 0, 0, 0 }),
			Size = vec(entry.size_studs or { 1, 1, 1 }),
			Transparency = transparency,
		}
		-- the game's settings the build chose for this mesh (rbx_fidelity: its collision shape from the empty space
		-- a cheaper shape would turn solid, its level of detail from pixels on the screen): Models.spawn asks
		-- Roblox for them when it creates the MeshPart. An older manifest has none: Roblox's defaults.
		if COLLISION[entry.collision_fidelity] then
			attributes.CollisionFidelity = entry.collision_fidelity
		end
		if RENDER[entry.render_fidelity] then
			attributes.RenderFidelity = entry.render_fidelity
		end
		-- a.physics (the manifest's physics): the group's own friction, bounce and density - Models.spawn gives
		-- the part Roblox's PhysicalProperties from them. None said: the engine's own for the part.
		if type(entry.physics) == "table" then
			for key, attr in { density = "PhysDensity", friction = "PhysFriction", elasticity = "PhysElasticity" } do
				if type(entry.physics[key]) == "number" then
					attributes[attr] = entry.physics[key]
				end
			end
		end
		-- a part broken beforehand (a.fracture, the manifest's fracture): the WHOLE's group is what shows until it
		-- breaks, its pieces' groups are spawned hidden; Models.shatter swaps them
		for part, f in manifest.fracture or {} do
			if type(f) == "table" then
				if f.whole == g then
					attributes.Whole = part
				end
				for _, piece in f.groups or {} do
					if piece == g then
						attributes.Shard = part
					end
				end
			end
		end
		-- a moving part (a.joint in the build script): Models.spawn makes it a Motor6D, not a weld
		for jname, j in manifest.joints or {} do
			if j.group == g then
				attributes.Joint = jname
				attributes.JointKind = j.kind
				attributes.JointParent = j.parent or "main"
				attributes.JointAxis = vec(j.axis)
				attributes.JointPivot = vec(j.pivot)
				attributes.JointMin = j.min or 0
				attributes.JointMax = j.max or 0
				-- a joint that FOLLOWS another (a.couple): posing the driver poses it (Models.pose)
				if type(j.follows) == "table" and type(j.follows.joint) == "string" then
					attributes.JointFollows = j.follows.joint
					attributes.JointRatio = j.follows.ratio or 1
					attributes.JointOffset = j.follows.offset or 0
				end
			end
		end
		table.insert(children, {
			name = g,
			className = "Folder",
			attributes = attributes,
			children = {
				{ name = "SurfaceAppearance", className = "SurfaceAppearance", properties = props },
			},
		})
	end
	-- named points the game needs (muzzle, sight line...): Models.spawn makes each an Attachment on Root
	local attributes: { [string]: any } = { Asset = asset }
	-- a MODULE of a kit (a.module in the build script): the cell it snaps by and the cells it takes, for the code
	-- that places it (0 on an axis the grid leaves free)
	if type(manifest.module) == "table" and type(manifest.module.grid) == "table" then
		attributes.ModuleGrid = vec(manifest.module.grid)
		if type(manifest.module.cells) == "table" then
			attributes.ModuleCells = vec(manifest.module.cells)
		end
	end
	-- THE FAR STAND-IN (a.far in the build script): Roblox's own name for it (Enum.ModelLevelOfDetail);
	-- Models.spawn sets the model's LevelOfDetail from it
	if manifest.far == "Automatic" or manifest.far == "StreamingMesh" or manifest.far == "Disabled" then
		attributes.Far = manifest.far
	end
	for anchor, at in manifest.anchors or {} do
		attributes["Anchor_" .. anchor] = vec(at)
	end
	-- THE MODEL'S OWN MOTION (a.cycle in the build script; rbx_cycleplay): each action cycle as the table the game
	-- plays - every joint's value over time - one StringValue a cycle under "Cycles". Models.play reads it and moves
	-- the spawned model's joints. A cycle the build did not sample (an older manifest) is left out.
	local cycles = {}
	for _, cycle in manifest.cycles or {} do
		if type(cycle.play) == "table" and type(cycle.name) == "string" then
			local value = serde.encode("json", cycle.play)
			-- (a string property is held to about 200,000 characters: a cycle that long is said here, not lost)
			if #value > CYCLE_MAX then
				error(
					`models: {asset}'s cycle "{cycle.name}" is {#value} characters as a table ({#(cycle.play.times or {})} keys): `
						.. `over the {CYCLE_MAX} a model file's value holds - a shorter cycle, or fewer frames a second`
				)
			end
			table.insert(cycles, { name = cycle.name, className = "StringValue", properties = { Value = value } })
		end
	end
	if #cycles > 0 then
		table.sort(cycles, function(a, b)
			return a.name < b.name
		end)
		table.insert(children, { name = "Cycles", className = "Folder", children = cycles })
	end
	-- A MODEL'S OWN RIG (a.reach in the build script; rbx_ik): each chain as what the game needs to solve it -
	-- its joints from the base outward WITH their pivots, axes and limits at rest, its tip, its named poses -
	-- one StringValue a chain under "Chains". Models.reach reads it.
	local chains = {}
	for cname, chain in manifest.chains or {} do
		local links, whole = {}, true
		for _, jname in chain.joints or {} do
			local j = (manifest.joints or {})[jname]
			if type(j) ~= "table" then
				-- (a chain naming a joint the manifest has not: said, never dropped without a word)
				error(`models: {asset}'s chain "{cname}" names the joint "{jname}", which the manifest has not`)
			end
			table.insert(
				links,
				{ name = jname, kind = j.kind, pivot = j.pivot, axis = j.axis, min = j.min or 0, max = j.max or 0 }
			)
		end
		if whole and #links > 0 then
			table.insert(chains, {
				name = cname,
				className = "StringValue",
				properties = {
					Value = serde.encode(
						"json",
						{ joints = links, tip = chain.tip, span = chain.span, poses = chain.poses or {} }
					),
				},
			})
		end
	end
	if #chains > 0 then
		table.sort(chains, function(a, b)
			return a.name < b.name
		end)
		table.insert(children, { name = "Chains", className = "Folder", children = chains })
	end
	local model = {
		className = "Folder",
		attributes = attributes,
		children = children,
	}
	return model, missing
end

-- a built manifest that never ships AS BUILT: rbx.Asset(private=True) — a study of someone else's design, built and
-- judged on this machine only — or stage="master" — the no-limits original, whose `kit optimize` game version ships
function Models.unshipped(m: any): boolean
	return type(m) == "table" and (m.private == true or m.stage == "master")
end

-- the assets among built manifests ({ [file name] = decoded manifest }) that never ship as built (Models.unshipped)
function Models.unshippedAssets(manifests: { [string]: any }): { string }
	local out = {}
	for file, m in manifests do
		local asset = string.match(file, "^(.+)%.manifest%.json$")
		if asset and Models.unshipped(m) then
			table.insert(out, asset)
		end
	end
	table.sort(out)
	return out
end

-- does a built file (its name without the extension) belong to one of `private` (unshipped assets)? Its mesh, its
-- groups' meshes (<asset>_<group>) and its maps (<asset>_color, <asset>_<group>_rough ...) are all named after it
function Models.isPrivateFile(stem: string, private: { string }): boolean
	for _, p in private do
		if stem == p or string.sub(stem, 1, #p + 1) == p .. "_" then
			return true
		end
	end
	return false
end

return Models

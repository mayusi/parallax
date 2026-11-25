--!strict
-- worldseason.luau (kit) — ONE WORLD IN SEVERAL SEASONS (the owner's method list: "Seasonal world variation").
-- A blueprint is written once, as it stands in its own season; its "seasons" say what each OTHER season changes,
-- and "season" says which one this build is:
--   "seasons": { "winter": { "lighting": "frost", "ambient": "snow",
--                            "terrain": { "Grass": "Snow", "LeafyGrass": "Snow", "Mud": "Glacier" },
--                            "palette": { "leaf": { "material": "Snow", "color": [236, 240, 246] } },
--                            "skip": [ "Flower beds" ] } },
--   "season": "winter"            (or false: the world as written)
-- What a season may change:
--   lighting, day, wind, ambient, weather, decoration, terrainColors, cover   the season's own, in place of the world's
--                (false: no lighting / day / wind / ambient / colours this season; for "weather" and
--                "decoration" false is their own word - never changes / no grass - and is kept)
--   terrain    { "<Material>": "<Material>" }: every terrain material of the world swapped - the ground and each
--              "heightmap" land (what lies under it, its rock, its patches and layers, every role the painter
--              paints), blocks, balls and cylinders, the worn trails of paths, the worn skirt under buildings.
--              WATER swapped to a solid ("Water": "Glacier") becomes a block of it: a lake that freezes over
--   palette    entries of the world's palette, re-made (the same names: what the steps already use)
--   skip       names of build steps left out this season
-- A season is a BUILD of the world: the same streets, walls and land, another surface and air. It is chosen when the
-- world is built, not while the game runs (Roblox cannot repaint a map's terrain between two frames).
-- Pure: no files, no instances. kit/test/spec/worldseason.spec.luau
local Environment = require("./environment")

local Season = {}

-- what a season may say, and how
local WHOLE = { "lighting", "day", "wind", "ambient", "weather", "decoration", "terrainColors", "cover" }
local KEYS: { [string]: boolean } = { terrain = true, palette = true, skip = true }
for _, k in WHOLE do
	KEYS[k] = true
end

-- the painter's material for each role of a heightmap op (kit/lib/environment.luau reads the same table)
function Season.roleMaterials(spec: any): { [string]: string }
	return Environment.paintDefaults(spec)
end

local function stepNames(bp: any): { [string]: boolean }
	local names: { [string]: boolean } = {}
	for _, step in bp.build do
		if type(step) == "table" then
			local _, spec = next(step)
			if type(spec) == "table" and type(spec.name) == "string" then
				names[spec.name] = true
			end
		end
	end
	return names
end

-- every terrain material a blueprint's land is made of (what a "terrain" swap can name)
function Season.materials(bp: any): { [string]: boolean }
	local used: { [string]: boolean } = {}
	for _, op in if type(bp.terrain) == "table" then bp.terrain else {} do
		if type(op) ~= "table" then
			continue
		end
		local kind, spec = next(op)
		if type(spec) ~= "table" then
			continue
		end
		local function use(m: any)
			if type(m) == "string" then
				used[m] = true
			end
		end
		use(spec.material or (if kind == "water" then "Water" else nil))
		use(spec.under)
		use(spec.rock)
		for _, p in if type(spec.patches) == "table" then spec.patches else {} do
			use(type(p) == "table" and p.material)
		end
		for _, l in if type(spec.layers) == "table" then spec.layers else {} do
			use(type(l) == "table" and l.material)
		end
		if kind == "heightmap" and spec.paint ~= false then
			-- (a painted heightmap: any of the painter's roles may be on it)
			for _, m in Season.roleMaterials(spec) do
				use(m)
			end
			for _, m in if type(spec.paint) == "table" then spec.paint else {} do
				use(m)
			end
		end
	end
	-- the worn trails of paths and the worn skirt under buildings are land too
	for _, step in if type(bp.build) == "table" then bp.build else {} do
		if type(step) == "table" then
			local _, spec = next(step)
			if type(spec) == "table" and type(spec.worn) == "string" then
				used[spec.worn] = true
			end
		end
	end
	if type(bp.contact) == "table" then
		used[if type(bp.contact.material) == "string" then bp.contact.material else "Ground"] = true
	end
	return used
end

-- what is wrong with a blueprint's "seasons" and "season" (every season is read, not only the one built)
function Season.problems(bp: any): { string }
	local out: { string } = {}
	if type(bp) ~= "table" or bp.seasons == nil then
		if type(bp) == "table" and bp.season ~= nil and bp.season ~= false then
			table.insert(out, `"season": "{tostring(bp.season)}" and no "seasons": say what each season changes`)
		end
		return out
	end
	if type(bp.seasons) ~= "table" or next(bp.seasons) == nil then
		return { '"seasons" is { "<name>": { what that season changes } }, one or more' }
	end
	local names = if type(bp.build) == "table" then stepNames(bp) else {}
	local land = Season.materials(bp)
	local sorted = {}
	for name in bp.seasons do
		table.insert(sorted, tostring(name))
	end
	table.sort(sorted)
	for _, name in sorted do
		local s = bp.seasons[name]
		local path = `seasons.{name}`
		if type(s) ~= "table" then
			table.insert(out, `{path} is \{ what the season changes }`)
			continue
		end
		local changes = 0
		for k, v in s do
			if not KEYS[k] then
				table.insert(
					out,
					`{path}.{tostring(k)}: a season changes lighting, day, wind, ambient, weather, decoration, terrainColors, terrain, palette, skip - nothing else`
				)
				continue
			end
			changes += 1
			if k == "terrain" then
				if type(v) ~= "table" or next(v) == nil then
					table.insert(out, `{path}.terrain is \{ "<Material>": "<Material>" }`)
					continue
				end
				for from, to in v do
					if not Environment.MATERIALS[from] or not Environment.MATERIALS[to] then
						table.insert(
							out,
							`{path}.terrain: "{tostring(from)}" -> "{tostring(to)}" - both are terrain materials (Grass, Ground, Rock, Sand, Mud, Snow, ...)`
						)
					elseif from == to then
						table.insert(out, `{path}.terrain: "{from}" -> "{to}" changes nothing`)
					elseif not land[from] then
						table.insert(
							out,
							`{path}.terrain: the world's land has no "{from}" to swap (it is made of what its "terrain" ops name)`
						)
					end
				end
			elseif k == "palette" then
				if type(v) ~= "table" or next(v) == nil then
					table.insert(out, `{path}.palette is \{ "<name>": \{ "material", "color" } }`)
					continue
				end
				for entry, made in v do
					if type(bp.palette) ~= "table" or bp.palette[entry] == nil then
						table.insert(
							out,
							`{path}.palette.{tostring(entry)}: the world's palette has no "{tostring(entry)}" - a season re-makes what the steps already use`
						)
					elseif type(made) ~= "table" or (made.material == nil and made.color == nil) then
						table.insert(out, `{path}.palette.{tostring(entry)} is \{ "material", "color" }`)
					end
				end
			elseif k == "skip" then
				if type(v) ~= "table" or #v == 0 then
					table.insert(out, `{path}.skip is a list of step names`)
					continue
				end
				for _, stepName in v do
					if type(stepName) ~= "string" or not names[stepName] then
						table.insert(out, `{path}.skip: no build step is named "{tostring(stepName)}"`)
					end
				end
			end
		end
		if changes == 0 then
			table.insert(out, `{path} changes nothing: a season says what is different in it`)
		end
	end
	if bp.season ~= nil and bp.season ~= false then
		if type(bp.season) ~= "string" or type(bp.seasons[bp.season]) ~= "table" then
			table.insert(
				out,
				`"season": "{tostring(bp.season)}" is none of this world's seasons ({table.concat(sorted, ", ")}; or false: the world as written)`
			)
		end
	end
	return out
end

local function swapped(spec: any, kind: string, swap: { [string]: string }): any
	local out = table.clone(spec)
	local function to(m: any): any
		return if type(m) == "string" and swap[m] then swap[m] else m
	end
	-- (a water op with no "material" is Water: said, so that it can be swapped - a lake that freezes)
	local own = spec.material or (if kind == "water" then "Water" else nil)
	if own ~= nil and swap[own] then
		out.material = swap[own]
	end
	out.under, out.rock = to(spec.under), to(spec.rock)
	for _, field in { "patches", "layers" } do
		if type(spec[field]) == "table" then
			local list = {}
			for i, item in spec[field] do
				if type(item) == "table" then
					local copy = table.clone(item)
					copy.material = to(item.material)
					list[i] = copy
				else
					list[i] = item
				end
			end
			out[field] = list
		end
	end
	if kind == "heightmap" and spec.paint ~= false then
		-- the painter's role map, as the WORLD's season has it (its defaults follow the op's own material and
		-- rock: read from the op as written), each role's material swapped
		local roles = Season.roleMaterials(spec)
		local paint = {}
		for role, m in roles do
			paint[role] = to(m)
		end
		for role, m in if type(spec.paint) == "table" then spec.paint else {} do
			paint[role] = to(m)
		end
		-- (an op that paints with "layers" and never asked for the painter keeps to its layers)
		if spec.paint ~= nil or spec.layers == nil then
			out.paint = paint
		end
	end
	return out
end

-- the blueprint as it stands in the season `name` (nil or false: as written). Never changes `bp`; with problems
-- (Season.problems) it hands `bp` back as it is - the compiler reports them.
function Season.apply(bp: any, name: any): any
	if name == nil or name == false or type(bp) ~= "table" or type(bp.seasons) ~= "table" then
		return bp
	end
	local s = bp.seasons[name]
	if type(s) ~= "table" or #Season.problems(bp) > 0 then
		return bp
	end
	local out = table.clone(bp)
	for _, k in WHOLE do
		if s[k] ~= nil then
			-- (false = the world has none this season; for a weather ("never changes"), the grass decoration
			-- ("off") and the cover ("bare, meant") false is their own word and stays)
			out[k] = if s[k] == false and k ~= "weather" and k ~= "decoration" and k ~= "cover" then nil else s[k]
		end
	end
	if s.palette then
		local palette = table.clone(bp.palette)
		for entry, made in s.palette do
			palette[entry] = made
		end
		out.palette = palette
	end
	if s.terrain and type(bp.terrain) == "table" then
		local ops = {}
		for i, op in bp.terrain do
			local kind, spec = next(op)
			if type(spec) ~= "table" then
				ops[i] = op
				continue
			end
			local made = swapped(spec, kind, s.terrain)
			-- WATER that a season makes solid is a block of it (the runtime fills every "water" op with water,
			-- whatever it names; the check would still read a lake no one can walk on)
			if kind == "water" and made.material ~= nil and made.material ~= "Water" then
				kind = "block"
				made.wasWater = true -- (a routed road still goes round it: kit/lib/world.luau)
			end
			ops[i] = { [kind] = made }
		end
		out.terrain = ops
	end
	if s.terrain then
		-- the worn trails of paths, the worn skirt under buildings
		local build = {}
		for i, step in bp.build do
			local kind, spec = next(step)
			if type(spec) == "table" and type(spec.worn) == "string" and s.terrain[spec.worn] then
				local copy = table.clone(spec)
				copy.worn = s.terrain[spec.worn]
				build[i] = { [kind] = copy }
			else
				build[i] = step
			end
		end
		out.build = build
		if type(bp.contact) == "table" then
			local skirt = if type(bp.contact.material) == "string" then bp.contact.material else "Ground"
			if s.terrain[skirt] then
				local contact = table.clone(bp.contact)
				contact.material = s.terrain[skirt]
				out.contact = contact
			end
		end
	end
	if s.skip then
		local gone: { [string]: boolean } = {}
		for _, stepName in s.skip do
			gone[stepName] = true
		end
		local build = {}
		for _, step in out.build do
			local _, spec = next(step)
			if not (type(spec) == "table" and type(spec.name) == "string" and gone[spec.name]) then
				table.insert(build, step)
			end
		end
		out.build = build
	end
	return out
end

-- the names of a world's seasons, sorted
function Season.names(bp: any): { string }
	local out = {}
	if type(bp) == "table" and type(bp.seasons) == "table" then
		for name in bp.seasons do
			table.insert(out, tostring(name))
		end
	end
	table.sort(out)
	return out
end

return Season

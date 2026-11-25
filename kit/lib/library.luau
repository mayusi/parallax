-- library.luau — the example library: proven content any project can start from (`kit new <kind> <name> --from
-- <example>`), and that grows (`kit promote`). Examples live in kit/starter/<dir>/; one-line descriptions in
-- kit/starter/library.json. Because kit/ is copied into every project and refreshed by `kit update`, an example
-- promoted into the kit's HOME copy reaches every project on its next update.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Library = {}

export type Kind = {
	dir: string, -- under kit/starter/
	file: (string) -> string, -- example name -> file name (folder kinds: the folder)
	pattern: string, -- file name -> example name
	folder: boolean?, -- multi-file example: a folder of template files (__NAME__ / __name__ placeholders)
}

Library.KINDS = {
	system = {
		dir = "systems",
		file = function(n: string): string
			return n
		end,
		pattern = "^([%w_]+)$",
		folder = true,
	},
	asset = {
		dir = "models",
		file = function(n: string): string
			return `build_{n}.py`
		end,
		pattern = "^build_(.+)%.py$",
	},
	sound = {
		dir = "sounds",
		file = function(n: string): string
			return `{n}.json`
		end,
		pattern = "^([^_].*)%.json$",
	},
	vfx = {
		dir = "vfx",
		file = function(n: string): string
			return `{n}.json`
		end,
		pattern = "^([^_].*)%.json$",
	},
	screen = {
		dir = "ui",
		file = function(n: string): string
			return `{n}.json`
		end,
		pattern = "^([^_].*)%.json$",
	},
	world = {
		dir = "worlds",
		file = function(n: string): string
			return `{n}.json`
		end,
		pattern = "^([^_].*)%.json$",
	},
	anim = {
		dir = "animations",
		file = function(n: string): string
			return `{n}.json`
		end,
		pattern = "^([^_].*)%.json$",
	},
} :: { [string]: Kind }

-- a v3 effect's dependencies: every part it uses and every texture its layers (and those parts' layers) name
function Library.vfxDeps(spec: any, partOf: (string) -> any): ({ string }, { string })
	local parts, textures, seenP, seenT = {}, {}, {}, {}
	local function scan(layers: any)
		if type(layers) ~= "table" then
			return
		end
		local function add(t: any)
			if type(t) == "string" and not seenT[t] then
				seenT[t] = true
				table.insert(textures, t)
			end
		end
		for _, el in layers do
			if type(el) == "table" then
				add(el.texture)
				-- the techniques' own textures (VfxTech / the world layers): boil shells, death puffs, lit variants,
				-- material overrides, the lens images
				add(type(el.boil) == "table" and el.boil.texture)
				add(type(el.onDeath) == "table" and el.onDeath.texture)
				add(el.dirtTexture)
				for _, t in (if type(el.lit) == "table" then el.lit else {}) :: any do
					add(t)
				end
				for _, over in (if type(el.onMaterial) == "table" then el.onMaterial else {}) :: any do
					add(type(over) == "table" and over.texture)
				end
				if el.kind == "lens" then
					add(if el.vignette ~= nil then "lens_vignette" else nil)
					add(if el.aberration ~= nil then "lens_fringe" else nil)
					add(if el.dirt ~= nil and el.dirtTexture == nil then "lens_dirt" else nil)
					add(if el.zoom ~= nil then "lens_zoom" else nil)
				end
			end
		end
	end
	if type(spec) ~= "table" then
		return parts, textures
	end
	scan(spec.layers)
	if type(spec.use) == "table" then
		for _, u in spec.use do
			if type(u) == "table" and type(u.part) == "string" and not seenP[u.part] then
				seenP[u.part] = true
				table.insert(parts, u.part)
				scan((partOf(u.part) or {}).layers)
			end
		end
	end
	table.sort(parts)
	table.sort(textures)
	return parts, textures
end

local function readJson(path: string): any
	if not fs.isFile(path) then
		return nil
	end
	local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return if ok then data else nil
end

local function ensureDir(path: string)
	if not fs.isDir(path) then
		fs.writeDir(path)
	end
end

-- pack an effect's dependencies into <starter>/vfx/_deps/<name>/: parts/, textures/ (specs + the finished pictures of
-- imported ones) and registry.json (the uploaded ids). paths: { vfx, textures, buildTextures }. Returns counts.
function Library.packVfx(starter: string, name: string, spec: any, paths: { [string]: string }): (number, number)
	local partOf = function(p: string): any
		return readJson(`{paths.vfx}/parts/{p}.json`)
	end
	local parts, textures = Library.vfxDeps(spec, partOf)
	local root = `{starter}/vfx/_deps/{name}`
	ensureDir(`{starter}/vfx/_deps`)
	ensureDir(root)
	ensureDir(`{root}/parts`)
	ensureDir(`{root}/textures`)
	for _, p in parts do
		local src = `{paths.vfx}/parts/{p}.json`
		if fs.isFile(src) then
			fs.writeFile(`{root}/parts/{p}.json`, fs.readFile(src))
		end
	end
	-- mesh sequences (shape "seq": assets/effects/seq/<name>.json) travel as they are
	for _, el in (if type(spec) == "table" and type(spec.layers) == "table" then spec.layers else {}) :: any do
		if
			type(el) == "table"
			and el.shape == "seq"
			and type(el.params) == "table"
			and type(el.params.seq) == "string"
		then
			local src = `{paths.vfx}/seq/{el.params.seq}.json`
			if fs.isFile(src) then
				ensureDir(`{root}/seq`)
				fs.writeFile(`{root}/seq/{el.params.seq}.json`, fs.readFile(src))
			end
		end
	end
	local registry = readJson(`{paths.vfx}/_textures.json`) or {}
	local carried = {}
	for _, t in textures do
		local specPath = `{paths.textures}/{t}.json`
		local tspec = readJson(specPath)
		if tspec then
			local png = `{paths.buildTextures}/{t}.png`
			if tspec.recipe == "import" and fs.isFile(png) then
				-- the download folder never travels: the finished picture does, and the spec imports that instead
				fs.writeFile(`{root}/textures/{t}.png`, fs.readFile(png))
				tspec.source = `__DEPS__/textures/{t}.png`
				fs.writeFile(`{root}/textures/{t}.json`, serde.encode("json", tspec, true))
			else
				fs.writeFile(`{root}/textures/{t}.json`, fs.readFile(specPath))
			end
		end
		if registry[t] ~= nil then
			carried[t] = registry[t]
		end
	end
	fs.writeFile(`{root}/registry.json`, serde.encode("json", carried, true))
	return #parts, #textures
end

-- the copies `kit new vfx <name> --from <example>` makes: { from, to } for every dependency the project lacks, plus
-- the registry entries it lacks (merged by the caller) and the import specs to rewrite (their source -> the copied picture)
function Library.unpackVfx(
	starter: string,
	example: string,
	paths: { [string]: string }
): ({ { from: string, to: string } }, { [string]: any })
	local root = `{starter}/vfx/_deps/{example}`
	local copies = {}
	if not fs.isDir(root) then
		return copies, {}
	end
	if fs.isDir(`{root}/parts`) then
		for _, f in fs.readDir(`{root}/parts`) do
			local to = `{paths.vfx}/parts/{f}`
			if not fs.isFile(to) then
				table.insert(copies, { from = `{root}/parts/{f}`, to = to })
			end
		end
	end
	if fs.isDir(`{root}/textures`) then
		for _, f in fs.readDir(`{root}/textures`) do
			local to = if string.sub(f, -4) == ".png" then `{paths.textures}/_library/{f}` else `{paths.textures}/{f}`
			if not fs.isFile(to) then
				table.insert(copies, { from = `{root}/textures/{f}`, to = to })
			end
		end
	end
	if fs.isDir(`{root}/seq`) then
		for _, f in fs.readDir(`{root}/seq`) do
			local to = `{paths.vfx}/seq/{f}`
			if not fs.isFile(to) then
				table.insert(copies, { from = `{root}/seq/{f}`, to = to })
			end
		end
	end
	local registry = readJson(`{root}/registry.json`) or {}
	return copies, registry
end

-- write an example's dependencies into a project (only what it lacks): the copies, the imported specs pointed at the
-- pictures that came with them, the uploaded ids merged into the project's registry. Returns the files written.
function Library.installVfx(starter: string, example: string, paths: { [string]: string }): { string }
	local copies, registry = Library.unpackVfx(starter, example, paths)
	local written = {}
	for _, c in copies do
		local parent = string.match(c.to, "^(.*)/[^/]+$")
		if parent and not fs.isDir(parent) then
			fs.writeDir(parent)
		end
		local body = fs.readFile(c.from)
		if string.sub(c.to, -5) == ".json" then
			body = string.gsub(body, "__DEPS__/textures/", paths.textures .. "/_library/")
		end
		fs.writeFile(c.to, body)
		table.insert(written, c.to)
	end
	if next(registry) ~= nil then
		local regPath = paths.vfx .. "/_textures.json"
		local reg = readJson(regPath)
		reg = if type(reg) == "table" then reg else {}
		local added = false
		for k, v in registry do
			if reg[k] == nil then
				reg[k] = v
				added = true
			end
		end
		if added then
			fs.writeFile(regPath, serde.encode("json", reg, true))
			table.insert(written, regPath)
		end
	end
	return written
end

-- root: the folder that holds kit/ (default: this project)
function Library.starter(root: string?): string
	return (if root and root ~= "" then root .. "/" else "") .. "kit/starter"
end

function Library.index(root: string?): { [string]: { [string]: string } }
	local path = Library.starter(root) .. "/library.json"
	if not fs.isFile(path) then
		return {}
	end
	local ok, data = pcall(serde.decode, "json", fs.readFile(path))
	return if ok and type(data) == "table" then data else {}
end

function Library.path(kind: string, name: string, root: string?): string?
	local k = Library.KINDS[kind]
	if not k then
		return nil
	end
	local p = `{Library.starter(root)}/{k.dir}/{k.file(name)}`
	if k.folder then
		return if fs.isDir(p) then p else nil
	end
	return if fs.isFile(p) then p else nil
end

-- { {name, about} } sorted by name
function Library.list(kind: string, root: string?): { { name: string, about: string } }
	local k = Library.KINDS[kind]
	local out = {}
	local dir = k and `{Library.starter(root)}/{k.dir}`
	if not dir or not fs.isDir(dir) then
		return out
	end
	local about = Library.index(root)[kind] or {}
	for _, f in fs.readDir(dir) do
		local n = string.match(f, k.pattern)
		if n and (fs.isDir(`{dir}/{f}`) == (k.folder == true)) then
			table.insert(out, { name = n, about = about[n] or "" })
		end
	end
	table.sort(out, function(a, b)
		return a.name < b.name
	end)
	return out
end

local function escape(s: string): string
	return (string.gsub(s, "[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0"))
end

-- an example's text, renamed to `name` (quoted names and build_<example> references)
function Library.renamed(text: string, example: string, name: string): string
	local out = string.gsub(text, `"{escape(example)}"`, `"{name}"`)
	out = string.gsub(out, `build_{escape(example)}%.py`, `build_{name}.py`)
	out = string.gsub(out, `kit asset {escape(example)}`, `kit asset {name}`)
	-- the example's own description ("STARTER: wooden supply crate") would now mislabel the new file
	out = string.gsub(out, "STARTER: ", `{name} — started from the "{example}" example: `, 1)
	return out
end

return Library

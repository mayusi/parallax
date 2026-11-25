-- integrity.luau — has anyone (an AI included) edited the kit's own files in this project?
-- `kit install` records a fingerprint of every kit-owned file (kit/MANIFEST.json); `kit status` re-checks it.
-- Edited kit files are the classic way a model "makes a gate pass". `kit sync` restores them from the home.
-- kit/starter, kit/lessons (grown by promote/lesson) and the bookkeeping files are not fingerprinted.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Integrity = {}

Integrity.MANIFEST = "kit/MANIFEST.json"
local ROOTS = { "kit", "src/kit", "parallax.luau" }
local SKIP = {
	"^kit/starter/",
	"^kit/lessons/",
	"^kit/HOME$",
	"^kit/MANIFEST%.json$",
	"__pycache__",
	"^kit/anchors/private/",
	"^kit/knowledge/vault/",
	"^kit/UPSTREAM%.json$",
	"^kit/types/globalTypes%.d%.luau$",
	"^kit/%.source$",
	-- the grading record a project grows in place when it has no kit home (kit grade / pairs / weights, the anchor
	-- sheet): the owner's data, never "an edited kit file" (kit/cmd/learn.luau canonical())
	"^kit/grades%.json$",
	"^kit/pairs%.json$",
	"^kit/weights%.json$",
	"^kit/anchors/",
}
-- (the knowledge vault is each project's own record: verdicts, orders and rules are written there on purpose)

-- FNV-1a 32-bit over the bytes, with line endings normalised (git may check files out with CRLF)
function Integrity.hash(text: string): string
	text = string.gsub(text, "\r\n", "\n")
	local h = 2166136261
	for i = 1, #text do
		h = bit32.bxor(h, string.byte(text, i))
		h = (h * 16777619) % 4294967296
	end
	return string.format("%08x", h)
end

local function skipped(path: string): boolean
	for _, pattern in SKIP do
		if string.find(path, pattern) then
			return true
		end
	end
	return false
end

-- { [relative path] = hash } for every kit-owned file under `base` ("" = here)
function Integrity.scan(base: string?): { [string]: string }
	local prefix = if base and base ~= "" then base .. "/" else ""
	local out = {}
	local function walk(rel: string)
		local full = prefix .. rel
		for _, name in fs.readDir(full) do
			local child = `{rel}/{name}`
			if not skipped(child) then
				if fs.isDir(prefix .. child) then
					walk(child)
				else
					out[child] = Integrity.hash(fs.readFile(prefix .. child))
				end
			end
		end
	end
	for _, root in ROOTS do
		if fs.isDir(prefix .. root) then
			walk(root)
		elseif fs.isFile(prefix .. root) then
			out[root] = Integrity.hash(fs.readFile(prefix .. root))
		end
	end
	return out
end

function Integrity.write(base: string?)
	local prefix = if base and base ~= "" then base .. "/" else ""
	fs.writeFile(prefix .. Integrity.MANIFEST, serde.encode("json", Integrity.scan(base), true) .. "\n")
end

local function inRoots(rel: string): boolean
	for _, root in ROOTS do
		if rel == root or string.sub(rel, 1, #root + 1) == root .. "/" then
			return true
		end
	end
	return false
end

-- the manifest for exactly the kit files an install, update or upgrade put there (`files`: their relative paths, as
-- the kit home or the release holds them): a file the project added under kit/ is never listed, so an upgrade never
-- takes it for one the kit installed (it removes only those) and `kit status` names it as added
function Integrity.writeOnly(base: string?, files: { string })
	local prefix = if base and base ~= "" then base .. "/" else ""
	local out = {}
	for _, rel in files do
		if inRoots(rel) and not skipped(rel) and fs.isFile(prefix .. rel) then
			out[rel] = Integrity.hash(fs.readFile(prefix .. rel))
		end
	end
	fs.writeFile(prefix .. Integrity.MANIFEST, serde.encode("json", out, true) .. "\n")
end

-- the files the kit itself writes beside its own while it runs and that change nothing the kit decides: never "added"
-- (a selftest build's parts sheet, Blender's backup of a .blend it saved). A file that feeds a gate is not one of
-- them: it is named like any file the kit did not install (a saliency calibration, a rig in the wrong name)
local ADDED_BY_THE_KIT = {
	"^kit/selftest/blender/[^/]+%.parts%.md$",
	"%.blend1$",
}
-- the rigs the kit ships (kit/anim/rigs/<name>.json, read by kit/lib/animrig.luau by the "rig" inside): a custom rig
-- `kit anim rig --from <probe>` wrote is named after the rig it holds and never claims a shipped rig's name - a file
-- that does (a planted zr6.json saying "R6") would replace the R6 the motion gates measure with, and is named
local SHIPPED_RIGS = { r6 = true, r15 = true }
local function customRig(prefix: string, path: string): boolean
	local file = string.match(path, "^kit/anim/rigs/([^/]+)%.json$")
	if not file then
		return false
	end
	local ok, data = pcall(function()
		return serde.decode("json", fs.readFile(prefix .. path))
	end)
	if not ok or type(data) ~= "table" or type(data.rig) ~= "string" then
		return false
	end
	local name = string.lower(data.rig)
	return name == file and not SHIPPED_RIGS[name]
end
local function addedByTheKit(prefix: string, path: string): boolean
	for _, pattern in ADDED_BY_THE_KIT do
		if string.find(path, pattern) then
			return true
		end
	end
	return customRig(prefix, path)
end

-- nil when there is no manifest (the kit's home, or a project installed before fingerprints existed)
-- base: optional project root (default = cwd)
function Integrity.check(base: string?): { changed: { string }, missing: { string }, added: { string } }?
	local prefix = if base and base ~= "" then base .. "/" else ""
	local manifest = prefix .. Integrity.MANIFEST
	if not fs.isFile(manifest) then
		return nil
	end
	local expected = serde.decode("json", fs.readFile(manifest))
	local now = Integrity.scan(base)
	local result = { changed = {}, missing = {}, added = {} }
	for path, hash in expected do
		if now[path] == nil then
			table.insert(result.missing, path)
		elseif now[path] ~= hash then
			table.insert(result.changed, path)
		end
	end
	for path in now do
		if expected[path] == nil and not addedByTheKit(prefix, path) then
			table.insert(result.added, path)
		end
	end
	for _, list in result do
		table.sort(list)
	end
	return result
end

return Integrity

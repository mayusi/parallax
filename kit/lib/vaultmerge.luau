-- vaultmerge.luau — how `kit install --update` brings the kit home's knowledge vault into a project WITHOUT wiping
-- what that project recorded itself. Everything else under kit/ is kit-owned and replaced; the vault is not: a
-- project's own verdicts, golden / graveyard rows, the owner's standing orders, its live rules, distil history and
-- inbox were written in that project and would be lost.
--   kit-owned pages (index.md, boot.md, README.md, *.base, _templates/)    replaced by the home's
--   golden.md, graveyard.md, orders.md                                       merged: the project's lines + the home's new
--   rules.md, distil.md, inbox.md, and every note (lessons, verdicts, ...)    the project's own; copied only when missing
local fs = require("@lune/fs")

local VaultMerge = {}

VaultMerge.PREFIX = "kit/knowledge/vault/"

local REPLACED = { ["index.md"] = true, ["boot.md"] = true, ["README.md"] = true }
local MERGED = { ["golden.md"] = true, ["graveyard.md"] = true, ["orders.md"] = true }

-- "replace" | "merge" | "keep" for a path relative to the vault root ("3d/golden.md", "ui/lessons/x.md")
function VaultMerge.policy(rel: string): string
	local name = string.match(rel, "([^/]+)$") or rel
	if REPLACED[name] or string.match(name, "%.base$") or string.find(rel, "_templates/", 1, true) then
		return "replace"
	end
	if MERGED[name] then
		return "merge"
	end
	return "keep"
end

-- the project's text with every line of the home's text it does not already hold appended (rows, orders): nothing
-- the project wrote is dropped or reordered
function VaultMerge.merge(projectText: string, homeText: string): string
	local p = string.gsub(projectText, "\r\n", "\n")
	local have: { [string]: boolean } = {}
	for line in string.gmatch(p, "[^\n]+") do
		have[line] = true
	end
	local add = {}
	for line in string.gmatch(string.gsub(homeText, "\r\n", "\n"), "[^\n]+") do
		if not have[line] and string.match(line, "%S") then
			have[line] = true
			table.insert(add, line)
		end
	end
	if #add == 0 then
		return projectText
	end
	return string.gsub(p, "%s+$", "") .. "\n" .. table.concat(add, "\n") .. "\n"
end

-- copy one vault file from the home (src) into the project (dst) by its policy; returns true when dst changed
function VaultMerge.copy(src: string, dst: string, rel: string): boolean
	local data = fs.readFile(src)
	if not fs.isFile(dst) then
		fs.writeFile(dst, data)
		return true
	end
	local policy = VaultMerge.policy(rel)
	local current = fs.readFile(dst)
	local out = if policy == "replace"
		then data
		elseif policy == "merge" then VaultMerge.merge(current, data)
		else current
	if out ~= current then
		fs.writeFile(dst, out)
		return true
	end
	return false
end

return VaultMerge

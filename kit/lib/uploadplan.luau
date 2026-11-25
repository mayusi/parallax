-- uploadplan.luau — the pure half of `kit upload`'s Studio route (no API key): the exact `open_cloud_invoke`
-- arguments the Roblox Studio MCP takes for one file, the experience grant, the asset id an agent hands back, and the
-- paths it may name either way. Pure (no file reads, no process): kit/test/spec/uploadplan.spec.luau proves it.
local serde = require("@lune/serde")

local UploadPlan = {}

UploadPlan.DESCRIPTION = "uploaded by the kit pipeline"
-- the Studio MCP's limits (open_cloud_invoke): asset files only, up to 20 MB each, from a folder the creator approved
UploadPlan.MAX_BYTES = 20 * 1024 * 1024
UploadPlan.SCOPES = { "asset:read", "asset:write" }
UploadPlan.GRANT_SCOPES = { "asset-permissions:write" }

-- a folder as a prefix: forward slashes, exactly one trailing slash
local function root(cwd: string): string
	local r = string.gsub(string.gsub(cwd, "\\", "/"), "/+$", "")
	return r .. "/"
end

-- a project-relative file -> its absolute path (forward slashes: the MCP reads files by absolute path)
function UploadPlan.absolute(file: string, cwd: string): string
	return root(cwd) .. (string.gsub(string.gsub(file, "\\", "/"), "^%./", ""))
end

-- a file named either way (relative, or the absolute path the plan printed; any slash, any drive-letter case) -> the
-- project-relative path
function UploadPlan.relative(file: string, cwd: string): string
	local f = string.gsub(file, "\\", "/")
	local r = root(cwd)
	if string.lower(string.sub(f, 1, #r)) == string.lower(r) then
		f = string.sub(f, #r + 1)
	end
	return (string.gsub(f, "^%./", ""))
end

-- the asset id an agent passes back: digits, or rbxassetid://<digits> - nothing else (an operation id or a path that
-- merely ENDS in digits would record a wrong id for good)
function UploadPlan.assetId(text: string?): string?
	if type(text) ~= "string" then
		return nil
	end
	return string.match(text, "^%s*rbxassetid://(%d+)%s*$") or string.match(text, "^%s*(%d+)%s*$")
end

-- the exact open_cloud_invoke arguments for one file: body is the JSON string to pass verbatim (the Assets API's
-- "request" form field as an object), files the multipart part, scopes what the creator must have granted
function UploadPlan.call(job: { file: string, assetType: string, name: string }, creator: any, cwd: string): any
	return {
		method = "POST",
		endpoint = "/assets/v1/assets",
		body = serde.encode("json", {
			request = {
				assetType = job.assetType,
				displayName = job.name,
				description = UploadPlan.DESCRIPTION,
				creationContext = { creator = creator },
			},
		}),
		files = { { name = "fileContent", path = UploadPlan.absolute(job.file, cwd) } },
		scopes = UploadPlan.SCOPES,
	}
end

-- the experience grant (so audio plays there): one call for every id of the plan
function UploadPlan.grant(universe: string, ids: { string }): any
	local requests = {}
	for _, id in ids do
		table.insert(requests, { assetId = id })
	end
	return {
		method = "PATCH",
		endpoint = "/asset-permissions-api/v1/assets/permissions",
		body = serde.encode(
			"json",
			{ subjectType = "Universe", subjectId = universe, action = "Use", requests = requests }
		),
		scopes = UploadPlan.GRANT_SCOPES,
	}
end

return UploadPlan

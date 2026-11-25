-- upgrade.luau — update the kit in this project from a GitHub Release (without a local kit clone).
-- Usage: lune run parallax upgrade [--check] [--tag vX.Y.Z] [--from <tarball.tar.gz> [--sha256 <hex|.sha256>]]
--        [--force] [--allow-dirty]
--
-- Zone 1 (core, atomically replaced): kit/** except starter/lessons/UPSTREAM.json/HOME/MANIFEST.json/.source/
--         globalTypes.d.luau/anchors/private/knowledge/vault; also src/kit/** and parallax.luau
-- Zone 2 (additive): kit/starter (copy missing), kit/lessons (append new lines), rokit.toml (add missing keys); the
--         project's .gitignore lines and scaffold come from the NEW kit's `init --no-starter` (the reconcile step),
--         never from the release's own .gitignore / kit.config.json (those are the kit repo's)
-- Zone 3 (policy-merged): kit/knowledge/vault — kit-owned pages replaced, golden/graveyard/orders appended,
--         rules/distil/inbox/notes kept (copy only if missing)
-- Zone 4 (untouched): everything else
local fs = require("@lune/fs")
local net = require("@lune/net")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Config = require("../lib/config")
local Integrity = require("../lib/integrity")
local Origin = require("../lib/origin")
local Run = require("../lib/run")
local VaultMerge = require("../lib/vaultmerge")

local C = Run.CODES
local Upgrade = {}

-- ── helpers ──────────────────────────────────────────────────────────────────

local function ts(): string
	-- a sortable timestamp safe for directory names, in UTC (local time can run backwards when a clock change sets it
	-- back, and a backup made then would sort before older ones)
	local t = os.time()
	local d = os.date("!*t", t) :: any
	return string.format("%04d%02d%02d-%02d%02d%02dZ", d.year, d.month, d.day, d.hour, d.min, d.sec)
end

local function sha256hex(bytes: string): string
	return string.lower(serde.hash("sha256", bytes))
end

-- read UPSTREAM.json from a project root (base = "" means cwd)
local function readUpstream(base: string?): { [string]: any }?
	local p = (if base and base ~= "" then base .. "/" else "") .. "kit/UPSTREAM.json"
	if not fs.isFile(p) then
		return nil
	end
	local ok, v = pcall(serde.decode, "json" :: any, fs.readFile(p))
	return if ok and type(v) == "table" then v else nil
end

local function writeUpstream(base: string?, data: { [string]: any })
	local p = (if base and base ~= "" then base .. "/" else "") .. "kit/UPSTREAM.json"
	fs.writeFile(p, serde.encode("json", data, true) .. "\n")
end

-- ── zone-classification helpers ───────────────────────────────────────────────

-- the files outside kit/ and src/kit/ an upgrade may write (zone 1: the entry point; zone 2: the tool pins): backed up
-- with the kit and put back by a restore
local BACKUP_TOP_FILES = { "parallax.luau", "rokit.toml" }

-- paths that zone 1 never touches (kept by the project)
local ZONE1_SKIP_PATTERNS = {
	"^kit/starter/",
	"^kit/lessons/",
	"^kit/HOME$",
	"^kit/MANIFEST%.json$",
	"^kit/UPSTREAM%.json$",
	"^kit/%.source$",
	"^kit/types/globalTypes%.d%.luau$",
	"^kit/anchors/private/",
	"^kit/knowledge/vault/",
	-- the grading record (zone 2 below: a release's copy only where the project has none - the owner's grades, pairs,
	-- weights and anchors are never replaced)
	"^kit/grades%.json$",
	"^kit/pairs%.json$",
	"^kit/weights%.json$",
	"^kit/anchors/",
}
local GRADING_DATA = { "^kit/grades%.json$", "^kit/pairs%.json$", "^kit/weights%.json$", "^kit/anchors/" }

local function zone1Skipped(rel: string): boolean
	for _, pat in ZONE1_SKIP_PATTERNS do
		if string.find(rel, pat) then
			return true
		end
	end
	return false
end

local function isZone1(rel: string): boolean
	-- (src/kit/ with its slash: src/kit_shim/ or src/kitchen/ are the game's, never the kit's)
	return (string.sub(rel, 1, 4) == "kit/" or string.sub(rel, 1, 8) == "src/kit/" or rel == "parallax.luau")
		and not zone1Skipped(rel)
end

-- tar's arguments for this machine's tar: GNU tar (Git Bash's) reads "C:/..." as a remote host unless --force-local;
-- the bsdtar Windows ships has no such option and reads drive paths as they are
local gnuTar: boolean? = nil
local function tarArgs(args: { string }): { string }
	if gnuTar == nil then
		local ok, r = pcall(process.exec, "tar", { "--version" })
		gnuTar = ok and r.ok and string.find(r.stdout, "GNU tar", 1, true) ~= nil
	end
	if gnuTar then
		local out = { "--force-local" }
		for _, a in args do
			table.insert(out, a)
		end
		return out
	end
	return args
end

local function isZone3(rel: string): boolean
	return string.find(rel, "^" .. VaultMerge.PREFIX:gsub("/", "%%/")) ~= nil
		or string.sub(rel, 1, #VaultMerge.PREFIX) == VaultMerge.PREFIX
end

-- ── archive safety check ──────────────────────────────────────────────────────

-- returns nil if safe, or an error string if any entry is dangerous
local function checkArchive(tarball: string): string?
	-- every entry is a plain file or a folder: the verbose listing starts each line with the entry's type ("-" a file,
	-- "d" a folder; "l" a symbolic link, "h" a hard link, devices and fifos are refused - a link inside kit/ would
	-- bring a file from outside the release, e.g. from the home folder, into the project)
	local v = process.exec("tar", tarArgs({ "-tvzf", tarball }))
	if not v.ok then
		return "tar -tvzf failed: " .. v.stderr
	end
	for line in string.gmatch(v.stdout, "[^\r\n]+") do
		local kind = string.sub(line, 1, 1)
		if kind ~= "-" and kind ~= "d" then
			return "archive contains a link or a special entry (only files and folders may be in a release): " .. line
		end
	end
	local r = process.exec("tar", tarArgs({ "-tzf", tarball }))
	if not r.ok then
		return "tar -tzf failed: " .. r.stderr
	end
	for entry in string.gmatch(r.stdout, "[^\n]+") do
		-- absolute path (Unix or Windows drive letter)
		if string.sub(entry, 1, 1) == "/" then
			return "archive contains absolute path: " .. entry
		end
		if string.match(entry, "^%a:") then
			return "archive contains drive-letter path: " .. entry
		end
		-- path traversal
		if string.find(entry, "%.%.") then
			return "archive contains path traversal (..): " .. entry
		end
	end
	return nil
end

-- ── GitHub release fetch ──────────────────────────────────────────────────────

type ReleaseInfo = {
	tag: string,
	assetUrl: string,
	sha256Url: string,
}

local function fetchReleaseInfo(repo: string, tag: string?): (ReleaseInfo?, string?)
	local url = if tag
		then `https://api.github.com/repos/{repo}/releases/tags/{tag}`
		else `https://api.github.com/repos/{repo}/releases/latest`
	local ok, res = pcall(
		net.request,
		{
			url = url,
			method = "GET",
			headers = { Accept = "application/vnd.github+json", ["X-GitHub-Api-Version"] = "2022-11-28" },
		} :: any
	)
	if not ok or not res.ok then
		return nil, `GitHub API request failed: {if ok then res.statusCode else tostring(res)}`
	end
	local okJ, data = pcall(serde.decode, "json" :: any, res.body)
	if not okJ or type(data) ~= "table" then
		return nil, "could not parse GitHub release JSON"
	end
	local releaseTag: string = data.tag_name or ""
	local assetUrl, sha256Url = "", ""
	for _, asset in (data.assets or {}) do
		local name: string = asset.name or ""
		-- (the release assets are named parallax-v<version>.tar.gz; a name without the "v" is accepted too)
		if string.match(name, "^parallax%-v?[%d%.]+%.tar%.gz$") then
			assetUrl = asset.browser_download_url or ""
		elseif string.match(name, "^parallax%-v?[%d%.]+%.tar%.gz%.sha256$") then
			sha256Url = asset.browser_download_url or ""
		end
	end
	if assetUrl == "" then
		return nil, `no parallax-*.tar.gz asset in release {releaseTag}`
	end
	return { tag = releaseTag, assetUrl = assetUrl, sha256Url = sha256Url }, nil
end

local function downloadBytes(url: string): (string?, string?)
	local ok, res = pcall(net.request, { url = url, method = "GET" } :: any)
	if not ok or not res.ok then
		return nil, `download failed: {if ok then tostring(res.statusCode) else tostring(res)}: {url}`
	end
	return res.body, nil
end

-- ── staging / apply helpers ───────────────────────────────────────────────────

-- read all entries from the staging folder into { [rel-from-top] = fullPath }; a link found after extraction is
-- refused too (the listing check above is the first guard; this one holds whatever tar did) -> (entries, error)
local function collectStaging(stagingTop: string): ({ [string]: string }, string?)
	local out: { [string]: string } = {}
	local bad: string? = nil
	local function walk(dir: string, prefix: string)
		if bad or not fs.isDir(dir) then
			return
		end
		for _, name in fs.readDir(dir) do
			local full = dir .. "/" .. name
			local rel = if prefix == "" then name else prefix .. "/" .. name
			local okMeta, meta = pcall(fs.metadata, full)
			if not okMeta or meta.kind == "symlink" then
				bad = rel
				return
			end
			if meta.kind == "dir" then
				walk(full, rel)
			elseif meta.kind == "file" then
				out[rel] = full
			else
				bad = rel
				return
			end
		end
	end
	walk(stagingTop, "")
	if bad then
		return {}, "the extracted release holds a link or a special file: " .. bad
	end
	return out, nil
end

-- the digest in a .sha256 text or a --sha256 value: the first word of exactly 64 hex digits, any case (a bare
-- digest, or sha256sum's "<digest>  <file name>") -> lower case, or nil
local function digestOf(text: string): string?
	for word in string.gmatch(text, "%S+") do
		if #word == 64 and not string.find(word, "%X") then
			return string.lower(word)
		end
	end
	return nil
end
Upgrade.digestOf = digestOf

-- merge two rokit.toml files: add keys from src missing in dst (keeps comments)
local function mergeRokitToml(dst: string, srcData: string)
	local cur = if fs.isFile(dst) then fs.readFile(dst) else ""
	local added = {}
	for line in string.gmatch(srcData, "[^\n]+") do
		-- a tool line: foo = "bar/baz@1.2.3"
		local key = string.match(line, "^([%w%-_]+)%s*=")
		if key and not string.find(cur, key, 1, true) then
			table.insert(added, line)
		end
	end
	if #added > 0 then
		local sep = if cur == "" or string.sub(cur, -1) == "\n" then "" else "\n"
		fs.writeFile(dst, cur .. sep .. table.concat(added, "\n") .. "\n")
	end
end

-- add lines from src missing in dst file
local function appendMissingLines(dst: string, srcData: string)
	local cur = if fs.isFile(dst) then fs.readFile(dst) else ""
	local have: { [string]: boolean } = {}
	for line in string.gmatch(cur, "[^\n]+") do
		have[line] = true
	end
	local add = {}
	for line in string.gmatch(srcData, "[^\n]+") do
		if string.match(line, "%S") and not have[line] then
			have[line] = true
			table.insert(add, line)
		end
	end
	if #add > 0 then
		local sep = if cur == "" or string.sub(cur, -1) == "\n" then "" else "\n"
		fs.writeFile(dst, cur .. sep .. table.concat(add, "\n") .. "\n")
	end
end

-- ── backup ───────────────────────────────────────────────────────────────────

local function backup(root: string, stamp: string): (string, { string })
	-- (a fresh folder every time: two upgrades in one second never share one, so a restore holds only this one's copy)
	local backupDir = root .. "/.verify/upgrade-backup-" .. stamp
	local n = 1
	while fs.isDir(backupDir) do
		n += 1
		backupDir = `{root}/.verify/upgrade-backup-{stamp}-{n}`
	end
	Config.ensureDir(backupDir)
	local backed: { string } = {}
	local function copyTree(src: string, dst: string)
		if fs.isDir(src) then
			Config.ensureDir(dst)
			for _, name in fs.readDir(src) do
				copyTree(src .. "/" .. name, dst .. "/" .. name)
			end
		elseif fs.isFile(src) then
			local parent = string.match(dst, "^(.*)/[^/]+$")
			if parent then
				Config.ensureDir(parent)
			end
			fs.writeFile(dst, fs.readFile(src))
			table.insert(backed, dst)
		end
	end
	for _, zone1Root in { "kit", "src/kit" } do
		local src = root .. "/" .. zone1Root
		if fs.isDir(src) then
			copyTree(src, backupDir .. "/" .. zone1Root)
		end
	end
	-- the files an upgrade touches outside kit/: kept as they were, and whether they were there at all
	local had: { [string]: boolean } = {}
	for _, top in BACKUP_TOP_FILES do
		had[top] = fs.isFile(root .. "/" .. top)
		if had[top] then
			fs.writeFile(backupDir .. "/" .. top, fs.readFile(root .. "/" .. top))
			table.insert(backed, backupDir .. "/" .. top)
		end
	end
	fs.writeFile(backupDir .. "/.had.json", serde.encode("json", had))
	return backupDir, backed
end

-- the backup put back: kit/ and src/kit/ become exactly what the backup holds (a file the failed upgrade added goes,
-- one it removed or changed comes back - the manifest, UPSTREAM.json, starters, lessons and vault with them), and the
-- files outside kit/ an upgrade touches are as they were (or gone, if there were none)
local function restore(backupDir: string, root: string)
	local function mirror(src: string, dst: string)
		if fs.isDir(dst) then
			for _, name in fs.readDir(dst) do
				local d, s = dst .. "/" .. name, src .. "/" .. name
				if fs.isDir(d) then
					if fs.isDir(s) then
						mirror(s, d)
					else
						fs.removeDir(d)
					end
				elseif not fs.isFile(s) then
					fs.removeFile(d)
				end
			end
		end
		if fs.isDir(src) then
			Config.ensureDir(dst)
			for _, name in fs.readDir(src) do
				local s, d = src .. "/" .. name, dst .. "/" .. name
				if fs.isDir(s) then
					mirror(s, d)
				elseif not fs.isFile(d) or fs.readFile(d) ~= fs.readFile(s) then
					fs.writeFile(d, fs.readFile(s))
				end
			end
		end
	end
	for _, zone1Root in { "kit", "src/kit" } do
		local src = backupDir .. "/" .. zone1Root
		if fs.isDir(src) then
			mirror(src, root .. "/" .. zone1Root)
		elseif fs.isDir(root .. "/" .. zone1Root) then
			fs.removeDir(root .. "/" .. zone1Root) -- (it was not there before)
		end
	end
	local okHad, had = pcall(function()
		return serde.decode("json", fs.readFile(backupDir .. "/.had.json"))
	end)
	for _, top in BACKUP_TOP_FILES do
		if fs.isFile(backupDir .. "/" .. top) then
			fs.writeFile(root .. "/" .. top, fs.readFile(backupDir .. "/" .. top))
		elseif okHad and type(had) == "table" and had[top] == false and fs.isFile(root .. "/" .. top) then
			fs.removeFile(root .. "/" .. top)
		end
	end
end
Upgrade.restore = restore
Upgrade.backup = backup
Upgrade.checkArchive = checkArchive

-- ── apply zones ───────────────────────────────────────────────────────────────

-- apply zone 1: replace core files atomically; remove files that the new release no longer has
local function applyZone1(entries: { [string]: string }, _topFolder: string, root: string): { string }
	local changed: { string } = {}
	-- files in zone1 from the release (relative to project root)
	local releaseZone1: { [string]: boolean } = {}

	for rel, srcFull in entries do
		-- strip the top folder prefix: "parallax-9.9.9/kit/foo.luau" -> "kit/foo.luau"
		local stripped = string.match(rel, "^[^/]+/(.+)$") or rel
		if isZone1(stripped) then
			releaseZone1[stripped] = true
			local dst = root .. "/" .. stripped
			local data = fs.readFile(srcFull)
			local parent = string.match(dst, "^(.*)/[^/]+$")
			if parent then
				Config.ensureDir(parent)
			end
			if not fs.isFile(dst) or fs.readFile(dst) ~= data then
				fs.writeFile(dst, data)
				table.insert(changed, stripped)
			end
		end
	end

	-- remove the kit files the OLD kit installed (its manifest, kit/MANIFEST.json, written by install / update /
	-- upgrade) that the new release no longer has. A file you added under kit/ was never in that manifest: it stays.
	-- (No manifest: nothing is removed. A listed path that climbs out with ".." is never followed.)
	local okM, installed = pcall(function()
		return serde.decode("json", fs.readFile(root .. "/" .. Integrity.MANIFEST))
	end)
	if okM and type(installed) == "table" then
		for rel in installed :: { [any]: any } do
			if
				type(rel) == "string"
				and not string.find(rel, "..", 1, true)
				and not string.find(rel, "\\", 1, true)
				and isZone1(rel)
				and not releaseZone1[rel]
				and fs.isFile(root .. "/" .. rel)
			then
				fs.removeFile(root .. "/" .. rel)
				table.insert(changed, "REMOVED: " .. rel)
			end
		end
	end
	-- (parallax.luau is the kit's entry point: the release writes it above; one the old kit installed and a release
	-- no longer ships goes with the rest of the kit's dropped files)
	return changed
end

-- apply zone 2: additive only
local function applyZone2(entries: { [string]: string }, _topFolder: string, root: string): { string }
	local changed: { string } = {}
	for rel, srcFull in entries do
		local stripped = string.match(rel, "^[^/]+/(.+)$") or rel
		local grading = false
		for _, pat in GRADING_DATA do
			grading = grading or string.find(stripped, pat) ~= nil
		end

		-- kit/starter/* and the grading record (grades, pairs, weights, anchors): copy only missing files
		if string.sub(stripped, 1, 12) == "kit/starter/" or grading then
			local dst = root .. "/" .. stripped
			if not fs.isFile(dst) then
				local data = fs.readFile(srcFull)
				local parent = string.match(dst, "^(.*)/[^/]+$")
				if parent then
					Config.ensureDir(parent)
				end
				fs.writeFile(dst, data)
				table.insert(changed, stripped)
			end

		-- kit/lessons/*.md: append new lines not already present
		elseif string.sub(stripped, 1, 12) == "kit/lessons/" and string.sub(stripped, -3) == ".md" then
			local dst = root .. "/" .. stripped
			local before = if fs.isFile(dst) then fs.readFile(dst) else ""
			appendMissingLines(dst, fs.readFile(srcFull))
			local after = if fs.isFile(dst) then fs.readFile(dst) else ""
			if before ~= after then
				table.insert(changed, stripped)
			end

		-- rokit.toml: add missing tool keys
		elseif stripped == "rokit.toml" then
			local before = if fs.isFile(root .. "/rokit.toml") then fs.readFile(root .. "/rokit.toml") else ""
			mergeRokitToml(root .. "/rokit.toml", fs.readFile(srcFull))
			local after = if fs.isFile(root .. "/rokit.toml") then fs.readFile(root .. "/rokit.toml") else ""
			if before ~= after then
				table.insert(changed, "rokit.toml")
			end
		end
		-- (the release's own .gitignore and kit.config.json are the KIT REPO's - its ignore rules for client files, its
		-- home's settings - never a project's: a project's ignore lines come from the new kit's `init` in the reconcile
		-- step below, and new config defaults live in Config.DEFAULTS, read at run time)
	end
	return changed
end

-- apply zone 3: knowledge vault policy
local function applyZone3(entries: { [string]: string }, _topFolder: string, root: string): { string }
	local changed: { string } = {}
	for rel, srcFull in entries do
		local stripped = string.match(rel, "^[^/]+/(.+)$") or rel
		if isZone3(stripped) then
			local vaultRel = string.sub(stripped, #VaultMerge.PREFIX + 1) -- e.g. "3d/golden.md"
			local dst = root .. "/" .. stripped
			local srcData = fs.readFile(srcFull)
			local policy = VaultMerge.policy(vaultRel)
			if policy == "replace" then
				local parent = string.match(dst, "^(.*)/[^/]+$")
				if parent then
					Config.ensureDir(parent)
				end
				if not fs.isFile(dst) or fs.readFile(dst) ~= srcData then
					fs.writeFile(dst, srcData)
					table.insert(changed, stripped)
				end
			elseif policy == "merge" then
				local before = if fs.isFile(dst) then fs.readFile(dst) else ""
				local merged = VaultMerge.merge(before, srcData)
				if merged ~= before then
					local parent = string.match(dst, "^(.*)/[^/]+$")
					if parent then
						Config.ensureDir(parent)
					end
					fs.writeFile(dst, merged)
					table.insert(changed, stripped)
				end
			else -- keep: copy only if missing
				if not fs.isFile(dst) then
					local parent = string.match(dst, "^(.*)/[^/]+$")
					if parent then
						Config.ensureDir(parent)
					end
					fs.writeFile(dst, srcData)
					table.insert(changed, stripped)
				end
			end
		end
	end
	return changed
end

-- ── main upgrade logic (exposed for testing) ─────────────────────────────────

type UpgradeOpts = {
	check: boolean?,
	tag: string?,
	fromPath: string?,
	sha256: string?,
	force: boolean?,
	allowDirty: boolean?,
	root: string?, -- project root ("" or nil = cwd)
}

function Upgrade.run(opts: UpgradeOpts): number
	local root = if opts.root and opts.root ~= "" then string.gsub(opts.root, "/+$", "") else ""
	local rootPrefix = if root ~= "" then root .. "/" else ""

	-- refuse in the kit's own repo
	if fs.isFile(rootPrefix .. "kit/.source") then
		return Run.report(
			"upgrade",
			{},
			C.USAGE,
			"upgrade: refused — this is the kit's own repo (kit/.source exists); upgrade installs into projects, not the home",
			"to update a project: (in the home) lune run parallax install <project> --update"
		)
	end

	-- read UPSTREAM.json
	local upstream = readUpstream(root)
	if not upstream then
		return Run.report(
			"upgrade",
			{},
			C.USAGE,
			"upgrade: no kit/UPSTREAM.json — this project's kit is older than the updater (3.0.0): update it once from a clone of the kit, then upgrade works",
			"in a clone of github.com/mayusi/parallax: lune run parallax update <this project>   (or here, if it has a kit home: lune run parallax sync)"
		)
	end
	-- (a kit installed from a local clone: its VERSION may be ahead of the release it names - say so, and that `sync`
	-- updates from that clone while `upgrade` takes the GitHub release instead)
	local cloneNote = if upstream.source == "clone"
		then ` (installed from a local clone{if type(upstream.source_commit) == "string"
				and upstream.source_commit ~= ""
			then " at " .. string.sub(upstream.source_commit, 1, 10)
			else ""}: lune run parallax sync updates from it; upgrade takes the GitHub release instead)`
		else ""
	local repo: string = upstream.repo or "mayusi/parallax"
	local channel: string = upstream.channel or "stable"

	-- ── --check mode ──────────────────────────────────────────────────────────
	if opts.check then
		local info, err = fetchReleaseInfo(repo, opts.tag)
		if not info then
			return Run.report(
				"upgrade",
				{},
				C.TOOLCHAIN,
				"upgrade --check: " .. (err or "unknown error"),
				"check network / GitHub"
			)
		end
		local installed = upstream.installed_tag or "(unknown)"
		if info.tag == installed then
			return Run.report(
				"upgrade",
				{},
				C.PASS,
				`upgrade --check: already on {info.tag} (channel {channel}){cloneNote}`,
				"no upgrade needed"
			)
		end
		return Run.report(
			"upgrade",
			{},
			C.PASS,
			`upgrade --check: {installed} → {info.tag} available (channel {channel}){cloneNote}`,
			`lune run parallax upgrade{if opts.tag then " --tag " .. opts.tag else ""}`
		)
	end

	-- ── pre-flight: integrity check (unless --force) ───────────────────────────
	if not opts.force then
		local diff = Integrity.check(if root ~= "" then root else nil)
		if diff then
			local dirty: { string } = {}
			for _, p in diff.changed do
				table.insert(dirty, "  changed: " .. p)
			end
			if #dirty > 0 then
				for _, line in dirty do
					Run.out(line)
				end
				-- (`sync` restores them when a kit home put the kit's files here last; when a release did - an upgrade
				-- since the install, whatever kit/HOME names - or there is no home, git does: kit/lib/origin.luau)
				local hasHome = Origin.of(root) == "home"
				return Run.report(
					"upgrade",
					{},
					C.USAGE,
					`upgrade: {#dirty} core file(s) have local edits — restore them, or pass --force to replace them with the release's`,
					if hasHome
						then "lune run parallax sync   (restores them from the kit home), then upgrade again"
						else "git checkout -- <the files listed above>   (or: lune run parallax upgrade --force)"
				)
			end
		end
	end

	-- ── pre-flight: dirty git tree ─────────────────────────────────────────────
	if not opts.allowDirty then
		local gitOk, gitStatus =
			pcall(process.exec, "git", { "-C", if root ~= "" then root else ".", "status", "--porcelain" })
		if gitOk and gitStatus.ok and gitStatus.stdout ~= "" then
			return Run.report(
				"upgrade",
				{},
				C.USAGE,
				"upgrade: git tree has uncommitted changes — commit or stash first, or pass --allow-dirty",
				"git add -A && git commit -m 'wip' && lune run parallax upgrade"
			)
		end
	end

	-- ── get the tarball ────────────────────────────────────────────────────────
	local tarball: string
	local expectedSha: string

	if opts.fromPath then
		-- local tarball supplied
		tarball = opts.fromPath
		if not fs.isFile(tarball) then
			return Run.report("upgrade", {}, C.USAGE, `upgrade: --from file not found: {tarball}`, "check the path")
		end
		-- sha256 from --sha256 (a 64-hex-digit digest, or else a file holding one) or a sibling .sha256 file
		if opts.sha256 then
			local given = string.match(opts.sha256, "^%s*(.-)%s*$") :: string
			local direct = if #given == 64 and not string.find(given, "%X") then string.lower(given) else nil
			if direct then
				expectedSha = direct
			else
				if not fs.isFile(given) then
					return Run.report(
						"upgrade",
						{},
						C.USAGE,
						`upgrade: --sha256 is neither a 64-hex-digit digest nor a file: {given}`,
						"pass the digest, or the release's .sha256 file"
					)
				end
				local digest = digestOf(fs.readFile(given))
				if not digest then
					return Run.report(
						"upgrade",
						{},
						C.USAGE,
						`upgrade: no SHA-256 digest in {given}`,
						"the .sha256 file holds a 64-hex-digit digest (optionally followed by the file name)"
					)
				end
				expectedSha = digest
			end
		else
			local sibling = tarball .. ".sha256"
			local digest = if fs.isFile(sibling) then digestOf(fs.readFile(sibling)) else nil
			if digest then
				expectedSha = digest
			else
				return Run.report(
					"upgrade",
					{},
					C.USAGE,
					"upgrade: --from requires --sha256 <hex or .sha256 file> (or a sibling <tarball>.sha256)",
					"lune run parallax upgrade --from parallax-x.y.z.tar.gz --sha256 parallax-x.y.z.tar.gz.sha256"
				)
			end
		end
		-- verify sha256
		local actual = sha256hex(fs.readFile(tarball))
		if actual ~= expectedSha then
			return Run.report(
				"upgrade",
				{},
				C.BUILD,
				`upgrade: SHA-256 mismatch — expected {expectedSha}, got {actual}`,
				"redownload the tarball"
			)
		end
	else
		-- fetch from GitHub
		local info, err = fetchReleaseInfo(repo, opts.tag)
		if not info then
			return Run.report(
				"upgrade",
				{},
				C.TOOLCHAIN,
				"upgrade: " .. (err or "unknown error"),
				"check network / GitHub"
			)
		end

		local installed = upstream.installed_tag or ""
		if installed == info.tag and not opts.force then
			return Run.report(
				"upgrade",
				{},
				C.PASS,
				`upgrade: already on {info.tag} — nothing to do (pass --force to reinstall){cloneNote}`,
				"no upgrade needed"
			)
		end

		-- fetch sha256 first
		if info.sha256Url ~= "" then
			local shaBytes, shaErr = downloadBytes(info.sha256Url)
			if not shaBytes then
				return Run.report(
					"upgrade",
					{},
					C.TOOLCHAIN,
					"upgrade: could not download sha256: " .. (shaErr or ""),
					"check network"
				)
			end
			local digest = digestOf(shaBytes)
			if not digest then
				return Run.report(
					"upgrade",
					{},
					C.BUILD,
					"upgrade: the release's .sha256 asset holds no SHA-256 digest",
					"cannot verify integrity without sha256"
				)
			end
			expectedSha = digest
		else
			return Run.report(
				"upgrade",
				{},
				C.BUILD,
				"upgrade: no .sha256 asset in release " .. info.tag,
				"cannot verify integrity without sha256"
			)
		end

		local assetBytes, assetErr = downloadBytes(info.assetUrl)
		if not assetBytes then
			return Run.report(
				"upgrade",
				{},
				C.TOOLCHAIN,
				"upgrade: download failed: " .. (assetErr or ""),
				"check network"
			)
		end

		-- verify before extracting
		local actual = sha256hex(assetBytes)
		if actual ~= expectedSha then
			return Run.report(
				"upgrade",
				{},
				C.BUILD,
				`upgrade: SHA-256 mismatch — expected {expectedSha}, got {actual}`,
				"the release asset may be corrupted; try again"
			)
		end

		-- write to staging area
		local stagingBase = rootPrefix .. ".verify/upgrade-staging"
		Config.ensureDir(stagingBase)
		tarball = stagingBase .. "/release.tar.gz"
		fs.writeFile(tarball, assetBytes)

		-- store resolved tag/sha for UPSTREAM.json update
		upstream._newTag = info.tag
		upstream._newSha = expectedSha
	end

	-- ── archive safety check ───────────────────────────────────────────────────
	local archiveErr = checkArchive(tarball)
	if archiveErr then
		return Run.report("upgrade", {}, C.BUILD, "upgrade: " .. archiveErr, "the archive is not safe to extract")
	end

	-- ── extract ────────────────────────────────────────────────────────────────
	local stagingDir = rootPrefix .. ".verify/upgrade-staging/extracted"
	if fs.isDir(stagingDir) then
		fs.removeDir(stagingDir)
	end
	Config.ensureDir(stagingDir)
	local extractResult = process.exec("tar", tarArgs({ "-xzf", tarball, "-C", stagingDir }))
	if not extractResult.ok then
		return Run.report(
			"upgrade",
			{},
			C.BUILD,
			"upgrade: tar extraction failed: " .. extractResult.stderr,
			"check the tarball"
		)
	end

	-- find the top folder (parallax-X.Y.Z/)
	local topFolder = ""
	if fs.isDir(stagingDir) then
		for _, name in fs.readDir(stagingDir) do
			if fs.isDir(stagingDir .. "/" .. name) then
				topFolder = name
				break
			end
		end
	end
	if topFolder == "" then
		return Run.report(
			"upgrade",
			{},
			C.BUILD,
			"upgrade: could not find top folder in extracted archive",
			"unexpected archive layout"
		)
	end

	local stagingTop = stagingDir .. "/" .. topFolder
	local entries, linkErr = collectStaging(stagingTop)
	if linkErr then
		fs.removeDir(stagingDir)
		return Run.report("upgrade", {}, C.BUILD, "upgrade: " .. linkErr, "the archive is not safe to install")
	end
	-- re-key relative to the top folder
	local staged: { [string]: string } = {}
	for rel, full in entries do
		staged[topFolder .. "/" .. rel] = full
	end

	-- ── backup ─────────────────────────────────────────────────────────────────
	local stamp = ts()
	local backupDir = backup(root ~= "" and root or ".", stamp)

	-- ── apply zones 1-3, then UPSTREAM.json and the manifest (one step: an error anywhere restores the backup) ──
	local newTag = ""
	local ok, applyErr = pcall(function()
		applyZone1(staged, topFolder, root ~= "" and root or ".")
		applyZone2(staged, topFolder, root ~= "" and root or ".")
		applyZone3(staged, topFolder, root ~= "" and root or ".")
		newTag = (upstream._newTag or opts.tag or upstream.installed_tag) :: string
		-- read VERSION from the new kit files
		local versionFile = rootPrefix .. "kit/VERSION"
		if fs.isFile(versionFile) then
			local v = string.gsub(fs.readFile(versionFile), "%s+", "")
			if newTag == "" or newTag == (upstream.installed_tag or "") then
				newTag = "v" .. v
			end
		end
		writeUpstream(root, {
			schema = 1,
			repo = repo,
			channel = channel,
			installed_tag = newTag,
			installed_sha256 = upstream._newSha or expectedSha,
			updated_at = os.date("!%Y-%m-%dT%H:%M:%SZ"),
			-- (a release FILE - `--from`: the tag may not be on GitHub, or the machine offline - so a restore names the
			-- file route; no path is kept: the record is committed with the game)
			source = if opts.fromPath then "file" else nil,
		})
		-- reconcile: fingerprint exactly the kit files this release brought (a file you added under kit/ is not one
		-- of them, so the next upgrade never removes it)
		local shipped: { string } = {}
		for rel in staged do
			table.insert(shipped, string.match(rel, "^[^/]+/(.+)$") or rel)
		end
		Integrity.writeOnly(root, shipped)
	end)
	if not ok then
		Run.out("[upgrade] error while applying — restoring backup: " .. tostring(applyErr))
		restore(backupDir, root ~= "" and root or ".")
		return Run.report(
			"upgrade",
			{},
			C.BUILD,
			"upgrade: apply failed — backup restored: " .. tostring(applyErr),
			"check disk space / permissions"
		)
	end

	-- the backups upgrades leave (each a whole copy of kit/): the three newest stay, older ones go
	do
		local verifyDir = rootPrefix .. ".verify"
		local backups = {}
		for _, nm in (if fs.isDir(verifyDir) then fs.readDir(verifyDir) else {}) :: { string } do
			if string.sub(nm, 1, 15) == "upgrade-backup-" and fs.isDir(verifyDir .. "/" .. nm) then
				table.insert(backups, nm)
			end
		end
		table.sort(backups)
		for i = 1, #backups - 3 do
			pcall(fs.removeDir, verifyDir .. "/" .. backups[i])
		end
	end

	-- ── post-upgrade: the NEW kit's init (idempotent: the project's .gitignore lines and scaffold, the git hooks, the
	-- connected clients - it runs the harness), then vault_migrate --dry-run ─────────────────────────────────────
	local harnessOk = true
	local harnessMsg = ""
	-- init's notes reach the person (one that finds what 3.0.0 wrote for every AI client removes it), and
	-- when no client is left connected the summary and the next step say to connect one
	local needsConnect = false
	do
		local cwd = if root ~= "" then root else process.cwd
		local hOk, hRes = pcall(process.exec, Run.tool("lune"), { "run", "kit", "init", "--no-starter" }, { cwd = cwd })
		if not hOk or not hRes.ok then
			harnessOk = false
			harnessMsg = " (init failed — run: lune run parallax init --no-starter)"
		else
			for line in string.gmatch(hRes.stdout, "[^\r\n]+") do
				local note = string.match(line, "^%s+!%s+(.+)$")
				if note then
					print("  ! " .. note)
				end
				if string.match(line, "^next_action:") and string.find(line, "parallax connect", 1, true) then
					needsConnect = true
				end
			end
		end
	end

	local vaultMsg = ""
	do
		local cwd = if root ~= "" then root else process.cwd
		local vOk, vRes = pcall(
			process.exec,
			Run.tool("python"),
			{ "kit/scripts/vault_migrate.py", "--dry-run" },
			{ cwd = cwd }
		)
		-- (the dry run's one JSON line says `pending`: everything it would file - the same count its --check and
		-- verify's "vault in step" read)
		local pending = 0
		if vOk and vRes.ok then
			local lines = string.split(string.gsub(vRes.stdout, "%s+$", ""), "\n")
			local okJ, counts = pcall(serde.decode, "json" :: any, lines[#lines] or "")
			if okJ and type(counts) == "table" and type(counts.pending) == "number" then
				pending = counts.pending
			end
		end
		if pending > 0 then
			vaultMsg = ` (the vault has {pending} item(s) to file — run: python kit/scripts/vault_migrate.py)`
		end
	end

	-- check if kit/mcp/server.py changed (prompt AI client restart)
	local mcpChanged = false
	for _, rel in { "kit/mcp/server.py" } do
		if fs.isFile(rootPrefix .. rel) then
			local backupMcp = backupDir .. "/" .. rel
			if fs.isFile(backupMcp) then
				if fs.readFile(rootPrefix .. rel) ~= fs.readFile(backupMcp) then
					mcpChanged = true
				end
			else
				mcpChanged = true
			end
		end
	end

	local restartHint = if mcpChanged then " — kit/mcp/server.py changed: RESTART your AI client" else ""
	local connectHint = if needsConnect
		then " — no AI client is connected to the kit now: lune run parallax connect <client>"
		else ""
	local summary =
		`upgrade: {upstream.installed_tag or "?"} → {newTag}{harnessMsg}{vaultMsg}{restartHint}{connectHint}`
	-- (the update is one commit across every lane: the lane fence lets it through with the word `cross`)
	local commitStep = '; then commit it on its own: git add -A; git commit -m "Update Parallax to '
		.. newTag
		.. ' (cross)"'
	if not harnessOk then
		-- (the kit's files ARE the new release and UPSTREAM names it - a second upgrade would say "already on" - but
		-- the new kit's init, which keeps the project in step with it, did not finish: that step is what is left)
		return Run.report(
			"upgrade",
			{},
			C.TOOLCHAIN,
			`upgrade: {upstream.installed_tag or "?"} → {newTag}: the kit's files are the new release, but its last step failed{harnessMsg}`,
			"lune run parallax init --no-starter   (then lune run parallax doctor" .. commitStep .. ")"
		)
	end
	local nextAction = if needsConnect
		then "lune run parallax connect <client> (claude, cursor, vscode, gemini, roo, opencode; codex, windsurf, cline, claude-desktop print their block), then lune run parallax doctor"
			.. commitStep
		else "lune run parallax doctor"
			.. (if vaultMsg ~= "" then "; python kit/scripts/vault_migrate.py" else "")
			.. commitStep

	return Run.report("upgrade", {}, C.PASS, summary, nextAction)
end

-- ── CLI registration ──────────────────────────────────────────────────────────

function Upgrade.register(Cli: any)
	Cli.command(
		"kit",
		"upgrade",
		"upgrade [--check] [--tag vX.Y.Z] [--from <tarball.tar.gz> [--sha256 <hex|file>]] [--force] [--allow-dirty]",
		"update the kit from a GitHub Release (no local kit clone needed)",
		function(args)
			local _, flags = Cli.parse(args)
			return Upgrade.run({
				check = flags.check == true,
				tag = type(flags.tag) == "string" and flags.tag or nil,
				fromPath = type(flags.from) == "string" and flags.from or nil,
				sha256 = type(flags.sha256) == "string" and flags.sha256 or nil,
				force = flags.force == true,
				allowDirty = flags["allow-dirty"] == true,
			})
		end
	)
end

return Upgrade

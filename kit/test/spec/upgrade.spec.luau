-- upgrade.spec.luau — the upgrade command: zone isolation, sha256 guard, path-traversal guard, dirty-edit guard.
-- Builds a small fake "release" tarball with zone-1/2/3 files, runs Upgrade.run with --from, and checks outcomes.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Upgrade = require("../../cmd/upgrade")

local TMP = "build/_upgradefix/"

-- ── helpers ───────────────────────────────────────────────────────────────────

local function ensureDir(path: string)
	local parts = string.split(path, "/")
	local cur = ""
	for _, p in parts do
		cur = if cur == "" then p else cur .. "/" .. p
		if cur ~= "" and not fs.isDir(cur) then
			fs.writeDir(cur)
		end
	end
end

local function put(root: string, rel: string, data: string)
	local full = root .. "/" .. rel
	local parent = string.match(full, "^(.*)/[^/]+$")
	if parent then
		ensureDir(parent)
	end
	fs.writeFile(full, data)
end

local function readOr(path: string, default: string): string
	if fs.isFile(path) then
		return fs.readFile(path)
	end
	return default
end

-- build a fake release tree and tar.gz it; returns (tarball path, sha256 hex). `drop`: files of the usual tree this
-- release does not ship
local function buildFakeRelease(releaseDir: string, version: string, drop: { string }?): (string, string)
	local top = releaseDir .. "/parallax-" .. version
	ensureDir(top)

	-- zone 1: core kit file
	put(top, "kit/VERSION", version .. "\n")
	put(top, "kit/init.luau", "-- fake init\nreturn {}\n")
	put(top, "kit/lib/fake_core.luau", "-- new core lib\nreturn {}\n")
	put(top, "src/kit/fake_runtime.luau", "-- new runtime\nreturn {}\n")
	put(top, "parallax.luau", "-- fake parallax entry\n")

	-- zone 2: starter (additive), lessons, rokit.toml, .gitignore, kit.config.json
	put(top, "kit/starter/models/StarterModel.blend", "fake blend data\n")
	put(top, "kit/lessons/3d.md", "# Lessons — 3D models\n\n- (tip1): a new lesson from release\n")
	put(top, "rokit.toml", '[tools]\nnewTool = "owner/newtool@1.0.0"\n')
	put(top, ".gitignore", "build/\n.verify/\nnewIgnore/\n")
	put(top, "kit.config.json", '{"newKey":"newVal","name":"SHOULD_NOT_OVERWRITE"}\n')

	-- the grading record a release ships (zone 2: only where the project has none)
	put(top, "kit/grades.json", '{"from":"the release"}\n')
	put(top, "kit/anchors/anchors.json", '{"from":"the release"}\n')
	put(top, "kit/anchors/release_anchor.png", "release anchor\n")

	-- zone 3: vault pages (policy-merged)
	put(top, "kit/knowledge/vault/3d/index.md", "# 3D index (replaced)\n")
	put(top, "kit/knowledge/vault/3d/golden.md", "# Golden\n\n- line from release\n")

	-- zone 4: a game file (untouched)
	put(top, "src/MyGame.luau", "-- zone 4 game file from release (should NOT appear in project)\n")

	for _, rel in drop or {} do
		fs.removeFile(top .. "/" .. rel)
	end
	local tarball = releaseDir .. "/parallax-" .. version .. ".tar.gz"
	local r = process.exec("tar", { "-czf", tarball, "-C", releaseDir, "parallax-" .. version })
	assert(r.ok, "tar create failed: " .. r.stderr)

	local bytes = fs.readFile(tarball)
	local sha = string.lower(serde.hash("sha256", bytes))
	local shaFile = tarball .. ".sha256"
	fs.writeFile(shaFile, sha .. "\n")

	return tarball, sha
end

-- build a minimal fake project root
local function buildFakeProject(projectDir: string, version: string)
	ensureDir(projectDir)
	-- existing zone-1 file that should be replaced
	put(projectDir, "kit/VERSION", "OLD_VERSION\n")
	put(projectDir, "kit/init.luau", "-- old init\n")
	put(projectDir, "kit/lib/old_only.luau", "-- this file is NOT in the release: should be removed\n")
	put(projectDir, "src/kit/old_runtime.luau", "-- old runtime\n")
	put(projectDir, "parallax.luau", "-- old entry\n")

	-- zone 2: existing starter file (should be KEPT, not overwritten)
	put(projectDir, "kit/starter/models/StarterModel.blend", "EXISTING PROJECT STARTER\n")
	-- existing lessons file with a line
	put(projectDir, "kit/lessons/3d.md", "# Lessons — 3D models\n\n- (old): existing lesson\n")
	-- existing rokit.toml
	put(projectDir, "rokit.toml", '[tools]\nexistingTool = "owner/existing@0.1.0"\n')
	-- existing .gitignore
	put(projectDir, ".gitignore", "build/\n.verify/\n")
	-- existing kit.config.json with a name set
	put(projectDir, "kit.config.json", '{"name":"MyProject"}\n')

	-- zone 3: existing vault
	put(projectDir, "kit/knowledge/vault/3d/golden.md", "# Golden\n\n- project own line\n")
	put(projectDir, "kit/knowledge/vault/3d/rules.md", "# Rules\n\nmy project rule\n")

	-- zone 4: a real game file (should be untouched)
	put(projectDir, "src/MyGame.luau", "-- project game code\n")

	-- MANIFEST.json (so Integrity.check can run)
	local Integrity = require("../../lib/integrity")
	Integrity.write(projectDir)

	-- UPSTREAM.json
	local upstreamData = {
		schema = 1,
		repo = "mayusi/parallax",
		channel = "stable",
		installed_tag = "v" .. version,
		installed_sha256 = "",
		updated_at = "2026-01-01T00:00:00Z",
	}
	put(projectDir, "kit/UPSTREAM.json", serde.encode("json", upstreamData, true) .. "\n")
end

-- ── clean up ──────────────────────────────────────────────────────────────────

local function fresh()
	if fs.isDir(TMP) then
		fs.removeDir(TMP)
	end
	fs.writeDir(TMP)
end

-- ── tests ─────────────────────────────────────────────────────────────────────

return function()
	test.suite("upgrade — zones", function()
		test.case(
			"zone 1 replaced, removed file gone; zone 2 additive; zone 3 merged; zone 4 untouched; UPSTREAM updated",
			function()
				fresh()
				local releaseDir = TMP .. "release"
				local projectDir = TMP .. "project"
				local version = "9.9.9"

				ensureDir(releaseDir)
				ensureDir(projectDir)

				local tarball, sha = buildFakeRelease(releaseDir, version)
				buildFakeProject(projectDir, "1.0.0")

				local code = Upgrade.run({
					fromPath = tarball,
					sha256 = sha,
					root = projectDir,
					allowDirty = true,
					force = true,
				})
				check.equal(code, 0)

				-- zone 1: core files replaced
				check.equal(readOr(projectDir .. "/kit/VERSION", ""), version .. "\n")
				check.equal(readOr(projectDir .. "/kit/init.luau", ""), "-- fake init\nreturn {}\n")
				check.equal(readOr(projectDir .. "/src/kit/fake_runtime.luau", ""), "-- new runtime\nreturn {}\n")
				check.equal(readOr(projectDir .. "/parallax.luau", ""), "-- fake parallax entry\n")

				-- zone 1: stale file removed
				check.equal(fs.isFile(projectDir .. "/kit/lib/old_only.luau"), false)

				-- zone 2: starter file NOT overwritten (project's own kept)
				check.equal(
					readOr(projectDir .. "/kit/starter/models/StarterModel.blend", ""),
					"EXISTING PROJECT STARTER\n"
				)

				-- zone 2: lessons appended (both old and new present)
				local lessons = readOr(projectDir .. "/kit/lessons/3d.md", "")
				check.equal(string.find(lessons, "existing lesson") ~= nil, true)
				check.equal(string.find(lessons, "a new lesson from release") ~= nil, true)

				-- zone 2: rokit.toml: new key added, old key kept
				local rokit = readOr(projectDir .. "/rokit.toml", "")
				check.equal(string.find(rokit, "existingTool") ~= nil, true)
				check.equal(string.find(rokit, "newTool") ~= nil, true)

				-- the release's OWN .gitignore and kit.config.json (the kit repo's) never reach the project: its ignore
				-- lines come from the new kit's init, its config defaults from Config.DEFAULTS
				local gitignore = readOr(projectDir .. "/.gitignore", "")
				check.equal(string.find(gitignore, "newIgnore/") == nil, true)
				check.equal(string.find(gitignore, "build/") ~= nil, true)
				local okJ, cfg = pcall(serde.decode, "json" :: any, readOr(projectDir .. "/kit.config.json", "{}"))
				check.equal(okJ, true)
				check.equal((cfg :: any).name, "MyProject")
				check.equal((cfg :: any).newKey, nil)

				-- zone 3: vault — index.md replaced, golden.md merged, rules.md kept
				local vaultIndex = readOr(projectDir .. "/kit/knowledge/vault/3d/index.md", "")
				check.equal(string.find(vaultIndex, "replaced") ~= nil, true)
				local vaultGolden = readOr(projectDir .. "/kit/knowledge/vault/3d/golden.md", "")
				check.equal(string.find(vaultGolden, "project own line") ~= nil, true)
				check.equal(string.find(vaultGolden, "line from release") ~= nil, true)
				local vaultRules = readOr(projectDir .. "/kit/knowledge/vault/3d/rules.md", "")
				check.equal(string.find(vaultRules, "my project rule") ~= nil, true)

				-- zone 4: game file untouched (project's; release version never written)
				check.equal(readOr(projectDir .. "/src/MyGame.luau", ""), "-- project game code\n")
				check.equal(fs.isFile(projectDir .. "/kit/knowledge/vault/3d/index.md"), true) -- just in case zone 4 leaked

				-- UPSTREAM.json updated
				local okU, up = pcall(serde.decode, "json" :: any, readOr(projectDir .. "/kit/UPSTREAM.json", "{}"))
				check.equal(okU, true)
				check.equal((up :: any).installed_tag, "v" .. version)
				-- (installed from a release FILE: the record says so - a restore names the file route - and it is
				-- still a release's record, never a clone's)
				check.equal((up :: any).source, "file")

				-- backup folder exists
				local verifyDir = projectDir .. "/.verify"
				local hasBackup = false
				if fs.isDir(verifyDir) then
					for _, name in fs.readDir(verifyDir) do
						if string.sub(name, 1, 15) == "upgrade-backup-" then
							hasBackup = true
						end
					end
				end
				check.equal(hasBackup, true)
			end
		)
	end)

	test.suite("upgrade — guards", function()
		test.case("wrong sha256 is refused; nothing changed", function()
			fresh()
			local releaseDir = TMP .. "guard_release"
			local projectDir = TMP .. "guard_project"
			ensureDir(releaseDir)
			ensureDir(projectDir)

			local tarball, _ = buildFakeRelease(releaseDir, "9.9.9")
			buildFakeProject(projectDir, "1.0.0")

			-- read the original VERSION before the (failed) upgrade
			local originalVersion = readOr(projectDir .. "/kit/VERSION", "")

			local code = Upgrade.run({
				fromPath = tarball,
				sha256 = "0000000000000000000000000000000000000000000000000000000000000000",
				root = projectDir,
				allowDirty = true,
				force = true,
			})
			-- should refuse with a non-zero code
			check.equal(code ~= 0, true)
			-- project files unchanged
			check.equal(readOr(projectDir .. "/kit/VERSION", ""), originalVersion)
		end)

		test.case("an archive with '..', an absolute path, a symlink or a hard link is refused; files pass", function()
			fresh()
			local evilDir = TMP .. "evil_release"
			ensureDir(evilDir)
			-- the archives are made by Python's tarfile (tar itself will not write a '..' or a link it cannot resolve)
			local script = table.concat({
				"import io, sys, tarfile",
				"def mk(name, members):",
				"    with tarfile.open(name, 'w:gz') as t:",
				"        for kind, path, extra in members:",
				"            ti = tarfile.TarInfo(path)",
				"            if kind == 'file':",
				"                data = extra.encode(); ti.size = len(data); t.addfile(ti, io.BytesIO(data))",
				"            elif kind == 'dir':",
				"                ti.type = tarfile.DIRTYPE; t.addfile(ti)",
				"            else:",
				"                ti.type = tarfile.SYMTYPE if kind == 'sym' else tarfile.LNKTYPE",
				"                ti.linkname = extra; t.addfile(ti)",
				"d = sys.argv[1]",
				"mk(d + '/ok.tar.gz', [('dir', 'parallax-9.9.9/', ''), ('file', 'parallax-9.9.9/kit/VERSION', '9.9.9')])",
				"mk(d + '/dots.tar.gz', [('file', 'parallax-9.9.9/../evil', 'x')])",
				"mk(d + '/abs.tar.gz', [('file', '/evil', 'x')])",
				"mk(d + '/sym.tar.gz', [('dir', 'parallax-9.9.9/', ''), ('sym', 'parallax-9.9.9/kit/key', '/home/u/.ssh/id_rsa')])",
				"mk(d + '/hard.tar.gz', [('file', 'parallax-9.9.9/kit/a', 'x'), ('hard', 'parallax-9.9.9/kit/b', 'parallax-9.9.9/kit/a')])",
			}, "\n")
			put(evilDir, "mk.py", script .. "\n")
			local Run = require("../../lib/run")
			local r = process.exec(Run.tool("python"), { evilDir .. "/mk.py", evilDir })
			assert(r.ok, "making the archives failed: " .. r.stderr)
			check.equal(Upgrade.checkArchive(evilDir .. "/ok.tar.gz"), nil)
			for name, why in { dots = "traversal", abs = "absolute", sym = "link", hard = "link" } do
				local err = Upgrade.checkArchive(`{evilDir}/{name}.tar.gz`)
				check.truthy(err ~= nil and string.find(err :: string, why, 1, true) ~= nil)
			end
		end)

		test.case("a file you added under kit/ stays; a file only the old kit installed goes", function()
			fresh()
			local releaseDir = TMP .. "keep_release"
			local projectDir = TMP .. "keep_project"
			ensureDir(releaseDir)
			ensureDir(projectDir)
			local tarball, sha = buildFakeRelease(releaseDir, "9.9.9")
			buildFakeProject(projectDir, "1.0.0")
			-- (after install: the old kit's manifest never listed it)
			put(projectDir, "kit/tools/my_own_tool.py", "print('mine')\n")
			local code =
				Upgrade.run({ fromPath = tarball, sha256 = sha, root = projectDir, allowDirty = true, force = true })
			check.equal(code, 0)
			check.equal(readOr(projectDir .. "/kit/tools/my_own_tool.py", ""), "print('mine')\n")
			check.equal(fs.isFile(projectDir .. "/kit/lib/old_only.luau"), false)
		end)

		test.case(
			"two upgrades in a row: your file under kit/ survives both; one the first release shipped goes",
			function()
				fresh()
				local projectDir = TMP .. "twice_project"
				ensureDir(projectDir)
				buildFakeProject(projectDir, "1.0.0")
				put(projectDir, "kit/tools/my_own_tool.py", "print('mine')\n") -- (added after install)
				local first, firstSha = buildFakeRelease(TMP .. "twice_release1", "9.9.9")
				check.equal(
					Upgrade.run({
						fromPath = first,
						sha256 = firstSha,
						root = projectDir,
						allowDirty = true,
						force = true,
					}),
					0
				)
				check.equal(fs.isFile(projectDir .. "/kit/lib/fake_core.luau"), true)
				-- the manifest names only what the release brought
				local okM, manifest =
					pcall(serde.decode, "json" :: any, readOr(projectDir .. "/kit/MANIFEST.json", "{}"))
				check.equal(okM, true)
				check.equal((manifest :: any)["kit/tools/my_own_tool.py"], nil)
				check.truthy((manifest :: any)["kit/lib/fake_core.luau"] ~= nil)
				local second, secondSha =
					buildFakeRelease(TMP .. "twice_release2", "9.9.10", { "kit/lib/fake_core.luau" })
				check.equal(
					Upgrade.run({
						fromPath = second,
						sha256 = secondSha,
						root = projectDir,
						allowDirty = true,
						force = true,
					}),
					0
				)
				check.equal(readOr(projectDir .. "/kit/tools/my_own_tool.py", ""), "print('mine')\n")
				check.equal(fs.isFile(projectDir .. "/kit/lib/fake_core.luau"), false)
				check.equal(readOr(projectDir .. "/kit/VERSION", ""), "9.9.10\n")
			end
		)

		test.case("the owner's grading record is kept: no --force needed, nothing of it replaced", function()
			fresh()
			local projectDir = TMP .. "grades_project"
			ensureDir(projectDir)
			buildFakeProject(projectDir, "1.0.0")
			-- (as installed, then graded here: kit grade / pairs / weights write in place when there is no kit home)
			put(projectDir, "kit/grades.json", '{"from":"the kit at install"}\n')
			put(projectDir, "kit/anchors/anchors.json", '{"from":"the kit at install"}\n')
			local Integrity = require("../../lib/integrity")
			Integrity.write(projectDir)
			put(projectDir, "kit/grades.json", '{"from":"the owner, graded"}\n')
			put(projectDir, "kit/anchors/anchors.json", '{"from":"the owner, graded"}\n')
			put(projectDir, "kit/anchors/owner_anchor.png", "the owner's anchor\n")
			local diff = Integrity.check(projectDir)
			check.equal(#(diff :: any).changed, 0) -- (grading is no edit of the kit)
			local tarball, sha = buildFakeRelease(TMP .. "grades_release", "9.9.9")
			check.equal(Upgrade.run({ fromPath = tarball, sha256 = sha, root = projectDir, allowDirty = true }), 0)
			check.equal(readOr(projectDir .. "/kit/grades.json", ""), '{"from":"the owner, graded"}\n')
			check.equal(readOr(projectDir .. "/kit/anchors/anchors.json", ""), '{"from":"the owner, graded"}\n')
			check.equal(readOr(projectDir .. "/kit/anchors/owner_anchor.png", ""), "the owner's anchor\n")
			check.equal(readOr(projectDir .. "/kit/anchors/release_anchor.png", ""), "release anchor\n") -- (added)
		end)

		test.case("a .sha256 is read in sha256sum's form or as a bare digest, any case", function()
			local hex = string.rep("ab12", 16)
			check.equal(Upgrade.digestOf(string.upper(hex)), hex)
			check.equal(Upgrade.digestOf(hex .. "  parallax-v9.9.9.tar.gz\n"), hex)
			check.equal(Upgrade.digestOf("SHA256 (x) = nope"), nil)
			check.equal(Upgrade.digestOf(string.sub(hex, 2)), nil) -- (63 digits)
			fresh()
			local releaseDir = TMP .. "sum_release"
			local projectDir = TMP .. "sum_project"
			ensureDir(releaseDir)
			ensureDir(projectDir)
			local tarball, sha = buildFakeRelease(releaseDir, "9.9.9")
			buildFakeProject(projectDir, "1.0.0")
			-- the file as sha256sum writes it, upper case, beside a path that starts with a hex letter
			local sumFile = releaseDir .. "/b_digest.sha256"
			fs.writeFile(sumFile, string.upper(sha) .. "  parallax-9.9.9.tar.gz\n")
			local code = Upgrade.run({
				fromPath = tarball,
				sha256 = sumFile,
				root = projectDir,
				allowDirty = true,
				force = true,
			})
			check.equal(code, 0)
			check.equal(readOr(projectDir .. "/kit/VERSION", ""), "9.9.9\n")
		end)

		test.case(
			"a restore puts kit/ back exactly (an added file goes, a removed one returns) and rokit.toml",
			function()
				fresh()
				local projectDir = TMP .. "restore_project"
				ensureDir(projectDir)
				put(projectDir, "kit/VERSION", "1.0.0\n")
				put(projectDir, "kit/lib/kept.luau", "-- kept\n")
				put(projectDir, "src/kit/Rt.luau", "-- runtime\n")
				local backupDir = Upgrade.backup(projectDir, "test")
				-- what a half-done upgrade leaves
				put(projectDir, "kit/VERSION", "9.9.9\n")
				put(projectDir, "kit/lib/added_by_release.luau", "-- new\n")
				fs.removeFile(projectDir .. "/kit/lib/kept.luau")
				put(projectDir, "rokit.toml", '[tools]\nnew = "a/b@1"\n') -- (there was none)
				Upgrade.restore(backupDir, projectDir)
				check.equal(readOr(projectDir .. "/kit/VERSION", ""), "1.0.0\n")
				check.equal(readOr(projectDir .. "/kit/lib/kept.luau", ""), "-- kept\n")
				check.equal(fs.isFile(projectDir .. "/kit/lib/added_by_release.luau"), false)
				check.equal(readOr(projectDir .. "/src/kit/Rt.luau", ""), "-- runtime\n")
				check.equal(fs.isFile(projectDir .. "/rokit.toml"), false)
			end
		)

		test.case("local edit to core file refused without --force", function()
			fresh()
			local releaseDir = TMP .. "edit_release"
			local projectDir = TMP .. "edit_project"
			ensureDir(releaseDir)
			ensureDir(projectDir)

			local tarball, sha = buildFakeRelease(releaseDir, "9.9.9")
			buildFakeProject(projectDir, "1.0.0")

			-- dirty: edit a core file (not in SKIP)
			local coreFile = projectDir .. "/kit/init.luau"
			fs.writeFile(coreFile, "-- EDITED BY TEST\n")
			-- update MANIFEST so the edit is detectable (the manifest was written before the edit)
			-- The integrity check compares current state to the manifest; re-write so the manifest reflects the original
			-- (buildFakeProject calls Integrity.write; then we edited the file above -> now it should detect the change)

			local code = Upgrade.run({
				fromPath = tarball,
				sha256 = sha,
				root = projectDir,
				allowDirty = true,
				-- NOT force
			})
			-- should refuse because kit/init.luau was edited
			check.equal(code ~= 0, true)
		end)

		test.case("refused in kit's own repo (kit/.source present)", function()
			fresh()
			local ownRepo = TMP .. "own_repo"
			ensureDir(ownRepo)
			put(ownRepo, "kit/.source", "")
			put(
				ownRepo,
				"kit/UPSTREAM.json",
				'{"schema":1,"repo":"mayusi/parallax","channel":"stable","installed_tag":"v3.0.0","installed_sha256":"","updated_at":"2026-01-01T00:00:00Z"}\n'
			)

			local code = Upgrade.run({
				fromPath = ownRepo .. "/fake.tar.gz",
				sha256 = "aabb",
				root = ownRepo,
				allowDirty = true,
				force = true,
			})
			check.equal(code ~= 0, true)
		end)
	end)
end

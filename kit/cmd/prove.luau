-- prove.luau — `kit prove`: prove the COMMITTED tree, not the working tree.
--
-- Several sessions share one checkout, so `kit verify` here is green only at a moment when nobody holds a
-- half-edited file — which never comes. `kit prove` checks the commit out into a sandbox worktree beside the
-- project (<project>-verify), gives it the untracked things verify needs (the package folders, the local data
-- folders, the build caches that are expensive to remake — by junction / symlink, read-mostly), its OWN folders for
-- the outputs the gates judge (build/ui, build/vfx, build/animations ... are generated there, so no other session's
-- live renders leak in), the games' empty asset folders git does not keep, then bakes what build/ needs (the
-- animations: base clips first, then the full bake — the re-arm steps read the R6 fold of their source) and runs
-- `kit verify` (and `kit selftest` with --selftest) IN the sandbox. Committed files (src/ui models, src/models,
-- library/*) are never regenerated there: a committed file that lags its source is exactly what the gates must say.
-- The verdict lands in THIS checkout's .verify/prove.json; `kit status` prints when the committed tree was last
-- proven and at which commit. Nothing in the sandbox is committed. NEVER `git worktree remove [--force]` it or
-- rm -rf it: its junctions point INTO this checkout and the delete follows them (2026-11-05 it emptied _artifacts,
-- _downloads, DevPackages and the build caches). Keep the sandbox (prove reuses it); to drop it, unlink every
-- junction first (`cmd /c rmdir <junction>`), then remove the folder.
--
--   lune run kit prove [--ref <sha|branch>] [--selftest] [--prepare] [--reuse-anim] [--dir <path>]
--     --prepare     set the sandbox up and stop (look at it, run gates by hand)
--     --reuse-anim  share build/animations with this checkout instead of baking (fast; another session's live
--                   bakes leak in; a stale clip is rebuilt INTO the shared folder)
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local task = require("@lune/task")

local Cli = require("../lib/cli")
local Config = require("../lib/config")
local Run = require("../lib/run")

local C = Run.CODES

-- the build subfolders the gates JUDGE: the sandbox gets its own (empty) copy of each, so the verdict is about this
-- commit's sources; everything else under build/ is a cache shared by junction (renders, textures, models, cad ...)
-- (build/vfxmeshes is NOT one of them: it is a Blender mesh cache the VFX previews read as INPUT, like build/textures;
-- an empty one made every mesh-layer preview differ from the library — planetary_cannon, 2026-10-17)
local OWN_BUILD = { ui = true, vfx = true, animations = true, moves = true, worlds = true }
-- untracked folders verify needs, shared by junction
local SHARED = { "DevPackages", "Packages", "ServerPackages", "_artifacts", "_downloads" }
-- the games' folders git keeps only when non-empty
local GAME_DIRS = {
	"assets/ui",
	"assets/animations",
	"assets/models",
	"assets/effects",
	"assets/sounds",
	"assets/worlds",
	"assets/net",
	"assets/moves",
	"src",
	"tests",
}
-- untracked files the kit reads
local COPY_FILES = { "games/.active", "kit.config.json", "parallax.config.json" }

local function slash(p: string): string
	return (string.gsub(p, "\\", "/"))
end

-- what a child kit command must be told: a variable written to process.env at runtime (Config.applyArgs' --profile /
-- --game) is NOT inherited by process.exec, so `kit prove --profile core` ran the sandbox's verify and anim with
-- every project (PARALLAX_FINAL_CLOSURE_SPEC A4, 2026-11-22). The profile, the game and the Parallax gate's nonce
-- travel explicitly, and the kit commands are also handed --profile (kitArgs)
local function childEnv(): { [string]: string }
	local e: { [string]: string } = {}
	local profile = Config.profile()
	if profile then
		e.PARALLAX_PROFILE = profile
		e.KIT_PROFILE = profile
	end
	local game = process.env.PARALLAX_GAME or process.env.KIT_GAME
	if type(game) == "string" and game ~= "" then
		e.PARALLAX_GAME = game
		e.KIT_GAME = game
	end
	local exempt = process.env.PARALLAX_EXEMPT
	if type(exempt) == "string" and #exempt >= 32 then
		e.PARALLAX_EXEMPT = exempt
	end
	return e
end

-- a child kit command's arguments: `lune run kit <cmd> ...` plus --profile <p> when a profile is active
local function kitArgs(cmd: { string }): { string }
	local out = { "run", "kit" }
	for _, a in cmd do
		table.insert(out, a)
	end
	local profile = Config.profile()
	if profile then
		table.insert(out, "--profile")
		table.insert(out, profile)
	end
	return out
end

local function exec(program: string, args: { string }, cwd: string?): (boolean, string)
	local opts: { [string]: any } = { env = childEnv() }
	if cwd then
		opts.cwd = cwd
	end
	local ok, r = pcall(process.exec, program, args, opts)
	if not ok then
		return false, tostring(r)
	end
	return r.ok, (r.stdout or "") .. (r.stderr or "")
end

local function git(args: { string }, cwd: string?): (boolean, string)
	local ok, out = exec("git", args, cwd)
	return ok, (string.gsub(out, "%s+$", ""))
end

-- a directory junction (Windows) or a symlink (elsewhere) from `link` to `target`
local function link(target: string, linkPath: string): boolean
	if fs.isDir(linkPath) or fs.isFile(linkPath) then
		return true
	end
	if process.os == "windows" then
		local ok =
			exec("cmd", { "/c", "mklink", "/J", (string.gsub(linkPath, "/", "\\")), (string.gsub(target, "/", "\\")) })
		return ok
	end
	local ok = exec("ln", { "-s", target, linkPath })
	return ok
end

local function basename(p: string): string
	return string.match(slash(p), "([^/]+)/?$") or p
end

-- the summary: / next_action: lines of a kit command's output
local function lines(out: string, key: string): string
	return string.match(out, "\n" .. key .. ": ([^\n]*)") or string.match(out, "^" .. key .. ": ([^\n]*)") or ""
end

-- the animation sources that are not re-arms / feels / warps: built first on a fresh build/animations (the python
-- re-arm steps run before the in-process R6 fold that writes what they read — kit anim's own order)
local function baseAnimSources(root: string): { string }
	local dir = `{root}/assets/animations`
	local out, seen = {}, {}
	if not fs.isDir(dir) then
		return out
	end
	for _, f in fs.readDir(dir) do
		if
			fs.isFile(`{dir}/{f}`)
			and f ~= "verdicts.json"
			and not string.match(f, "%.rearm%.json$")
			and not string.match(f, "%.feel%.json$")
			and not string.match(f, "%.warp%.json$")
			and not string.match(f, "%.derive%.json$")
		then
			local stem = string.match(f, "^([%w_]+)%.import%.json$")
				or string.match(f, "^([%w_]+)%.gait%.json$")
				or string.match(f, "^([%w_]+)%.pose%.json$")
				or string.match(f, "^([%w_]+)%.move%.json$")
				or string.match(f, "^([%w_]+)%.json$")
				or string.match(f, "^([%w_]+)%.blend$")
			if stem and not seen[stem] then
				seen[stem] = true
				table.insert(out, stem)
			end
		end
	end
	table.sort(out)
	return out
end

local function hasClips(dir: string): boolean
	if not fs.isDir(dir) then
		return false
	end
	for _, f in fs.readDir(dir) do
		if string.match(f, "%.clip%.json$") then
			return true
		end
	end
	return false
end

return function(Cli_: any)
	Cli_.command(
		"code",
		"prove",
		"prove [--ref <sha>] [--selftest] [--prepare] [--reuse-anim] [--dir <path>]",
		"prove the COMMITTED tree: check HEAD out into a sandbox worktree beside the project, give it what verify needs, bake build/, run kit verify (+ selftest) there; the verdict (sha, date) shows in kit status",
		function(rawArgs)
			local _, flags = Cli.parse(rawArgs)
			local root = slash(process.cwd)
			root = (string.gsub(root, "/+$", ""))
			local parent = string.match(root, "^(.*)/[^/]+$") or root
			local name = basename(root)
			local dir = if type(flags.dir) == "string" then slash(flags.dir) else `{parent}/{name}-verify`
			local ref = if type(flags.ref) == "string" then flags.ref else "HEAD"
			local okSha, sha = git({ "rev-parse", ref })
			if not okSha or sha == "" then
				return Run.report(
					"prove",
					{},
					C.TOOLCHAIN,
					`prove: not a git checkout, or no commit "{ref}"`,
					"run it in the project root of a git checkout"
				)
			end
			local steps = {}
			local function step(label: string, ok: boolean, detail: string)
				table.insert(steps, Run.step(label, ok, detail, { summary = detail })) -- Run.step prints the line
				return ok
			end

			-- 1. the sandbox at the commit (a fresh worktree, or the existing one moved to it: its local
			--    regenerations dropped, its baked build kept)
			local fresh = not fs.isDir(`{dir}/.git`) and not fs.isFile(`{dir}/.git`)
			if fresh then
				local ok, out = git({ "worktree", "add", "--detach", dir, sha })
				if not step("sandbox", ok, if ok then `new worktree {dir} at {string.sub(sha, 1, 8)}` else out) then
					return Run.report("prove", steps, C.TOOLCHAIN, "prove: could not make the sandbox worktree", out)
				end
			else
				git({ "checkout", "-q", "--", "." }, dir)
				git({ "clean", "-q", "-fd", "--", "library", "src", "kit/knowledge", "assets", "games" }, dir)
				local ok, out = git({ "checkout", "-q", "--detach", sha }, dir)
				-- an interrupted earlier move (the machine out of processes or memory mid-checkout) leaves the
				-- target's files behind as UNTRACKED in the sandbox: remove exactly the ones git names, retry once
				if not ok and string.find(out, "untracked working tree files would be overwritten", 1, true) then
					for path in string.gmatch(out, "\n\t([^\r\n]+)") do
						local p = `{dir}/{path}`
						if fs.isFile(p) then
							fs.removeFile(p)
						end
					end
					ok, out = git({ "checkout", "-q", "--detach", sha }, dir)
				end
				if not step("sandbox", ok, if ok then `{dir} moved to {string.sub(sha, 1, 8)}` else out) then
					return Run.report(
						"prove",
						steps,
						C.TOOLCHAIN,
						"prove: could not move the sandbox to the commit",
						out
					)
				end
			end
			-- every tracked file with the bytes the repository keeps (LF), as this checkout's tools wrote them: with
			-- core.autocrlf=true git checks them out as CRLF, the owner's clocks hash a piece's files byte for byte, and
			-- every piece past its budget read as "changed since its last build" - the sandbox's anim bake stopped on 8
			-- of them (2026-11-22), and a spec measuring a file's size in bytes (start.spec: the router <= 3500) read the
			-- CRLF copy. Re-written once, here; git still sees the tree clean (it compares normalised text)
			do
				local okL, listed = pcall(process.exec, "git", { "ls-files", "-z" }, { cwd = dir })
				if okL and listed.ok then
					for path in string.gmatch(listed.stdout, "([^%z]+)") do
						pcall(fs.removeFile, `{dir}/{path}`)
					end
					git({ "-c", "core.autocrlf=false", "checkout", "-q", "--", "." }, dir)
				end
			end

			-- 2. what verify needs and git does not keep
			local linked, made = {}, {}
			for _, d in SHARED do
				if fs.isDir(`{root}/{d}`) and not fs.isDir(`{dir}/{d}`) then
					if link(`{root}/{d}`, `{dir}/{d}`) then
						table.insert(linked, d)
					end
				end
			end
			if fs.isDir(`{root}/build`) then
				if not fs.isDir(`{dir}/build`) then
					fs.writeDir(`{dir}/build`)
				end
				for _, entry in fs.readDir(`{root}/build`) do
					local src, dst = `{root}/build/{entry}`, `{dir}/build/{entry}`
					if fs.isDir(src) then
						if OWN_BUILD[entry] and not (entry == "animations" and flags["reuse-anim"]) then
							if not fs.isDir(dst) then
								fs.writeDir(dst)
								table.insert(made, `build/{entry}`)
							end
						elseif not fs.isDir(dst) and link(src, dst) then
							table.insert(linked, `build/{entry}`)
						end
					elseif not fs.isFile(dst) then
						pcall(fs.copy, src, dst)
					end
				end
			end
			if fs.isDir(`{root}/games`) then
				for _, g in fs.readDir(`{root}/games`) do
					for _, sub in GAME_DIRS do
						if fs.isDir(`{root}/games/{g}/{sub}`) and not fs.isDir(`{dir}/games/{g}/{sub}`) then
							fs.writeDir(`{dir}/games/{g}/{sub}`)
						end
					end
				end
			end
			for _, f in COPY_FILES do
				if fs.isFile(`{root}/{f}`) and not fs.isFile(`{dir}/{f}`) then
					pcall(fs.copy, `{root}/{f}`, `{dir}/{f}`)
				end
			end
			-- the Parallax gate's FILED nonce goes with the sandbox (every run: it is minted anew): the children run in
			-- the sandbox, where the gate reads the sandbox's own .verify - without it the anim bake there was refused
			-- (2026-11-22, the first prove since the gate went live; the nonce itself travels in childEnv)
			local exemptFile = ".verify/parallax_exempt.json"
			if fs.isFile(`{root}/{exemptFile}`) then
				if not fs.isDir(`{dir}/.verify`) then
					pcall(fs.writeDir, `{dir}/.verify`)
				end
				pcall(fs.copy, `{root}/{exemptFile}`, `{dir}/{exemptFile}`, true)
			end
			step(
				"prepare",
				true,
				`{#linked} shared by junction, {#made} own build folder(s){if #made > 0
					then " (" .. table.concat(made, ", ") .. ")"
					else ""}`
			)
			if flags.prepare then
				return Run.report(
					"prove",
					steps,
					C.PASS,
					`prove: sandbox ready at {dir} ({string.sub(sha, 1, 8)})`,
					`cd {dir} && lune run kit verify   (or: lune run kit prove, to run it all)`
				)
			end

			-- 3b (started first). the UI art index the UI gates read (build/ui/art: the kit's drawn art + every identity's
			-- plates and its committed pictures). Build-only outputs: the committed models in src/ui are NOT regenerated,
			-- so a model that lags its spec still shows red. It runs BESIDE the animation bake (build/ui/art and
			-- build/animations share nothing - PARALLAX_FINAL_CLOSURE_SPEC A4); art before plates (one folder), and its
			-- results are recorded after the bake's, in the same order as before
			local uiSteps = {
				{ "ui art", { "kit/ui/art.py", "--out", "build/ui/art" } },
				{
					"ui plates",
					{ "kit/ui/plates.py", "--identities", "assets/ui/identities", "--out", "build/ui/art" },
				},
			}
			local uiResults: { { ok: boolean, out: string } } = {}
			local uiDone = false
			task.spawn(function()
				for _, s in uiSteps do
					local ok, out = exec(Run.tool("python"), s[2], dir)
					table.insert(uiResults, { ok = ok, out = out })
					if not ok then
						break
					end
				end
				uiDone = true
			end)

			-- 3. bake what build/ needs: the animations (the only generated thing a verify gate refuses to make)
			local lune = Run.tool("lune")
			local animDir = `{dir}/build/animations`
			if not hasClips(animDir) then
				local base = baseAnimSources(dir)
				if #base > 0 then
					print(`  baking {#base} base animation source(s) first (the re-arms read their R6 folds) ...`)
					local ok, out = exec(lune, kitArgs({ "anim", table.unpack(base) }), dir)
					if not step("anim base", ok, lines(out, "summary")) then
						return Run.report(
							"prove",
							steps,
							C.CONTENT,
							"prove: the base animations did not bake",
							lines(out, "next_action")
						)
					end
				end
			end
			do
				print("  the full bake ...")
				local ok, out = exec(lune, kitArgs({ "anim" }), dir)
				-- a re-arm runs before the R6 fold of its source (kit anim's own order): when a lane changed a SOURCE since
				-- the sandbox last baked (ClaymoreCombo from SwordCombo, 2026-10-18), the re-arm reads the old fold and is
				-- refused as stale. Bake the base sources first, then the full bake once more
				if not ok and string.find(out, "is stale (the clip it is built from", 1, true) then
					local base = baseAnimSources(dir)
					print(
						`  a re-arm read an old source fold: baking {#base} base source(s), then the full bake again ...`
					)
					exec(lune, kitArgs({ "anim", table.unpack(base) }), dir)
					ok, out = exec(lune, kitArgs({ "anim" }), dir)
				end
				if not step("anim bake", ok, lines(out, "summary")) then
					return Run.report(
						"prove",
						steps,
						C.CONTENT,
						"prove: the animation bake failed",
						lines(out, "next_action")
					)
				end
			end

			-- 3b (joined). the UI steps started beside the bake
			while not uiDone do
				task.wait(0.2)
			end
			for i, s in uiSteps do
				local r = uiResults[i]
				if r == nil then
					break
				end
				local ok, out = r.ok, r.out
				if not step(s[1], ok, lines(out, "summary")) then
					return Run.report(
						"prove",
						steps,
						C.CONTENT,
						`prove: the {s[1]} step failed`,
						lines(out, "next_action")
					)
				end
			end

			-- 4. the gates, in the sandbox
			print("  kit verify in the sandbox ...")
			local okV, outV = exec(lune, kitArgs({ "verify" }), dir)
			local verifySummary = lines(outV, "summary")
			local failing = string.match(outV, "\n%[FAIL%] ([^\n]*)")
			if failing then
				-- the gate's first detail lines name the file (stylua's "Diff in", selene's path, a stale model)
				local after = string.match(outV, "\n%[FAIL%] [^\n]*\n(.-)\nsummary:") or ""
				-- the line that names the FILE: selene prints its rule first and the path two lines down ("┌─ path:line"),
				-- stylua prints "Diff in <path>:", the in-process gates print the path first; else the first line
				local firstLine, pathLine = nil, nil
				local n = 0
				for l in string.gmatch(after, "[^\n]+") do
					if
						not string.match(l, "^%-%-%- ")
						and not string.match(l, "^%s*%[warn%]")
						and l ~= failing
						and string.match(l, "%S")
					then
						n += 1
						local clean = string.gsub(string.gsub(l, "^%s+", ""), ":%s*$", "")
						firstLine = firstLine or clean
						if
							not pathLine
							and (
								string.find(clean, "┌─", 1, true) or string.match(clean, "[%w_%-/\\%.]+%.%a+:?%d*")
							)
						then
							pathLine = (string.gsub(clean, "^.-┌─%s*", ""))
						end
						if n >= 8 then
							break
						end
					end
				end
				local named = pathLine or firstLine
				if named then
					failing ..= " — " .. string.sub(named, 1, 120)
				end
			end
			step("verify", okV, if okV then verifySummary else (failing or verifySummary))
			local okS, selfSummary = true, "not run (--selftest runs it)"
			if flags.selftest and okV then
				print("  kit selftest in the sandbox ...")
				local ok, outS = exec(lune, kitArgs({ "selftest" }), dir)
				okS = ok
				selfSummary = if ok
					then lines(outS, "summary")
					else (string.match(outS, "\n%[FAIL%] ([^\n]*)") or lines(outS, "summary"))
				step("selftest", ok, selfSummary)
			end
			local when = os.date("!%Y-%m-%d %H:%M UTC")
			local verdict = {
				sha = sha,
				ref = ref,
				dir = dir,
				when = when,
				verify = { ok = okV, summary = verifySummary, failing = failing },
				selftest = { ok = okS, summary = selfSummary, ran = flags.selftest == true },
			}
			if not fs.isDir(".verify") then
				fs.writeDir(".verify")
			end
			fs.writeFile(".verify/prove.last.json", serde.encode("json", verdict, true))
			local allOk = okV and okS
			return Run.report(
				"prove",
				steps,
				if allOk then C.PASS else C.CONTENT,
				if allOk
					then `prove: the committed tree {string.sub(sha, 1, 8)} is GREEN ({verifySummary}{if flags.selftest
						then "; " .. selfSummary
						else ""})`
					else `prove: {string.sub(sha, 1, 8)} is RED — {if not okV
						then failing or verifySummary
						else selfSummary}`,
				if allOk
					then "nothing — the commit holds; kit status shows the proof"
					else `the failing gate names a committed file: fix it in the checkout, commit, prove again (sandbox: {dir})`
			)
		end
	)
end

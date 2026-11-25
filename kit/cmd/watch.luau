-- watch.luau — WATCH MODE: rebuild an asset every time you save it, through a persistent Blender
-- (kit/lib/worker.luau: no Blender start-up per build — measured ~30% faster, identical verdicts).
--   kit watch <asset> [--geo] [--once]
-- Watches the build script, the asset's spec / trace / review (refs/<asset>*, assets/models/<asset>*): each save
-- rebuilds and prints the verdict's summary + next_action. A change to the kit itself restarts the worker. --geo: the
-- geometry-only check (seconds); --once: one build through the worker, then exit.
-- The full chain (lines, perceptual, export to the game) is `kit asset <asset>` — watch is the fast inner loop.
local fs = require("@lune/fs")
local task = require("@lune/task")

local Config = require("../lib/config")
local Content = require("./content")
local Run = require("../lib/run")
local Worker = require("../lib/worker")

-- every file this asset's build reads that a person edits: changed ones (by size + modified time) trigger a build
local function stamp(asset: string, script: string): string
	local parts = {}
	local function add(path: string)
		local ok, meta = pcall(fs.metadata, path)
		if ok and meta.exists and meta.kind == "file" and meta.modifiedAt then
			table.insert(parts, path .. "@" .. tostring(meta.modifiedAt.unixTimestampMillis))
		end
	end
	add(script)
	for _, dir in { "refs", Config.path("models") } do
		if fs.isDir(dir) then
			for _, name in fs.readDir(dir) do
				local own = string.sub(name, 1, #asset + 1) == asset .. "."
					or string.sub(name, 1, #asset + 1) == asset .. "_"
				-- (parts.md is rewritten by every build: answering it is picked up on the next save of anything else)
				if own and not string.find(name, "%.parts%.md$") then
					add(`{dir}/{name}`)
				end
			end
		end
	end
	table.sort(parts)
	return table.concat(parts, "|")
end

return function(Cli: any)
	Cli.command(
		"3d",
		"watch",
		"watch <asset> [--geo] [--once]",
		"rebuild an asset on every save through a persistent Blender (no start-up per build) — the fast inner loop",
		function(rawArgs)
			local asset = rawArgs[1]
			local script = if asset then `{Config.path("models")}/build_{asset}.py` else ""
			if not asset or not fs.isFile(script) then
				return Run.report(
					"watch",
					{},
					Run.CODES.USAGE,
					`watch: needs an asset with a build script ({script ~= "" and script or "assets/models/build_<asset>.py"})`,
					"lune run kit watch crate   (or kit new asset <name> first)"
				)
			end
			local args = { "--no-preview" }
			if table.find(rawArgs, "--geo") then
				args = { "--geo" }
			end
			local once = table.find(rawArgs, "--once") ~= nil
			-- the owner's stage approvals hold here as in kit asset: any build needs the model sheet's, a baked one
			-- (no --geo) the blockout's too (a watch that skipped them was a way round the lock)
			local staged = require("../lib/lanelocks").stages(
				asset,
				nil,
				nil,
				if table.find(rawArgs, "--geo") then "geo" else "full"
			)
			if staged then
				return Run.report(
					"watch",
					{},
					Run.CODES.CONTENT,
					`watch: {asset} skipped a stage approval (model sheet / blockout)`,
					staged
				)
			end
			local h, why = Worker.start(if once then 120 else 1800)
			if not h then
				return Run.report(
					"watch",
					{},
					Run.CODES.TOOLCHAIN,
					`watch: {why}`,
					"check that Blender runs: lune run kit doctor"
				)
			end
			print(
				`watch: {asset} — building through the worker on 127.0.0.1:{h.port}; save to rebuild, Ctrl+C to stop`
			)
			local last = ""
			local builds = 0
			local result: any = nil
			while true do
				local now = stamp(asset, script)
				if now ~= last then
					-- the clock and the route, before EVERY rebuild (this is the inner loop a rework would spin in)
					local stop = Content.prebuild(asset, Config.path("models"))
					if stop then
						if h then
							Worker.stop(h :: any)
						end
						return Run.report("watch", {}, Run.CODES.CONTENT, stop.summary, stop.next_action)
					end
					local r = Worker.build(h :: any, script, args)
					-- the kit's code changed since the worker started, or the worker is gone (idled out, crashed, stopped
					-- by its own starter): a fresh one builds instead — once; a second failure is reported
					if r.restart or r.error then
						print(
							if r.restart
								then "watch: the kit changed — restarting the worker"
								else `watch: {r.error} — starting a fresh worker`
						)
						h, why = Worker.start(if once then 120 else 1800)
						if not h then
							return Run.report("watch", {}, Run.CODES.TOOLCHAIN, `watch: {why}`, "lune run kit doctor")
						end
						r = Worker.build(h :: any, script, args)
					end
					builds += 1
					result = r
					local v = r.verdict
					if r.error then
						print(`[FAIL] watch #{builds}: {r.error}`)
					elseif not v then
						print(`[FAIL] watch #{builds}: the build crashed before its verdict ({r.seconds} s):`)
						print(string.sub(r.output or "", -1500))
					else
						print(
							`[{if v.status == "pass" then "ok" else "FAIL"}] watch #{builds} ({r.seconds} s): {v.summary}`
						)
						print(`  next_action: {v.next_action}`)
						if v.preview then
							print(`  look at: {v.preview}`)
						end
					end
					last = now -- (the files as they were when this build started: a save made during it is built next)
					if once then
						break
					end
				end
				task.wait(0.5)
			end
			if h then
				Worker.stop(h :: any)
			end
			local v = result and result.verdict
			return Run.report(
				"watch",
				{},
				if v and v.status == "pass" then Run.CODES.PASS else Run.CODES.CONTENT,
				if v
					then `watch: {asset} built through the worker in {result.seconds} s — {v.summary}`
					else "watch: no verdict",
				if v then v.next_action else "read the output above"
			)
		end
	)
end

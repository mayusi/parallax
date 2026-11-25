-- upload.luau — `kit upload`: put every built asset on Roblox through Open Cloud and record the ids, so nobody
-- uploads by hand. What goes up (only new or changed files — assets/uploads.json remembers what is live):
--   build/textures/*.png            Image      -> VFX texture registry (flipbooks on) + ids.textures
--   build/models/*.fbx              Mesh       -> ids.models   } then src/models/<asset>.model.json is rewritten,
--   build/models/textures/*.png     Image      -> ids.textures } so Models.spawn("<asset>") builds the real model
--   build/vfxmeshes/*.fbx           Mesh       -> VFX mesh registry (replaces the stand-in shapes)
--   build/worldmeshes/*.fbx + .png  Mesh/Image -> ids.worldmeshes / ids.worldtextures (kit WorldMeshes places them)
--   build/ui/art/*.png              Image      -> ids.ui (screens' "art:<name>" images; kit ui recompiles)
--   build/sounds/*.ogg              Audio      -> ids.sounds (Assets.play)
--   KitAnimations in the built place  Animation (.rbxm) -> ids.animations (Anim.play)
-- Every file is screened first (the moderation gate: banned words, blood) and only new or changed files go.
-- THE ROUTE (no API key): the Roblox Studio MCP calls Open Cloud with the creator's own Studio login. `kit upload`
-- writes build/upload_plan.json - for every file the exact `open_cloud_invoke` call (POST /assets/v1/assets, the
-- request, the file's absolute path, the scopes) - and the agent makes those calls, polls each operation, and records
-- the id: `kit upload --record <file> <assetId>` (into the same ledger and id files as ever; the last one recompiles
-- models + screens and prints the experience grant). `kit upload --pending` shows what is left.
-- Headless (CI, no Studio): with ROBLOX_API_KEY set in the environment the kit uploads itself (never pass the key on
-- the command line, never write it to a file); `--studio` takes the Studio route even then.
-- Owner + experience come from kit.config.json "upload": {"creator": "user:<id>" | "group:<id>", "universe": <id>} -
-- with a universe set, audio (and everything else) is granted to it so it plays there. New images/audio go through
-- Roblox moderation first: `kit upload --status` shows where they are.
local fs = require("@lune/fs")
local net = require("@lune/net")
local process = require("@lune/process")
local serde = require("@lune/serde")
local stdio = require("@lune/stdio")
local task = require("@lune/task")

local AssetIds = require("../lib/assetids")
local Board = require("../lib/board")
local Config = require("../lib/config")
local Content = require("./content")
local Integrity = require("../lib/integrity")
local Moderation = require("../lib/moderation")
local Run = require("../lib/run")
local UploadJobs = require("../lib/uploadjobs")
local UploadPlan = require("../lib/uploadplan")

local C = Run.CODES
local API = "https://apis.roblox.com/assets/v1"
local LEDGER = Config.path("uploads")
local MIME = { png = "image/png", ogg = "audio/ogg", fbx = "model/fbx", rbxm = "model/x-rbxm" }

type Job = { file: string, assetType: string, name: string }

-- the Studio route's plan (build/: transient, never committed)
local function planPath(): string
	return Config.build("upload_plan.json")
end

local function readPlan(): any?
	local path = planPath()
	if not fs.isFile(path) then
		return nil
	end
	local ok, plan = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return if ok and type(plan) == "table" and type(plan.files) == "table" then plan else nil
end

local function savePlan(plan: any)
	local path = planPath()
	Config.ensureDir((string.match(path, "^(.*)/[^/]*$") or "."))
	fs.writeFile(path, serde.encode("json", plan, true) .. "\n")
end

local function ledger(): { [string]: any }
	return if fs.isFile(LEDGER) then serde.decode("json", fs.readFile(LEDGER)) else {}
end

local function saveLedger(l: { [string]: any })
	Config.ensureDir((string.match(LEDGER, "^(.*)/[^/]*$") or "."))
	fs.writeFile(LEDGER, serde.encode("json", l, true) .. "\n")
end

local function multipart(request: string, file: string, bytes: string): (string, string)
	local boundary = "kitboundary" .. tostring(math.floor(os.clock() * 1e6))
	local ext = string.match(file, "%.(%w+)$") or ""
	local filename = string.match(file, "([^/]+)$") or file
	local body = table.concat({
		`--{boundary}\r\n`,
		'Content-Disposition: form-data; name="request"\r\n',
		"Content-Type: application/json\r\n\r\n",
		request,
		`\r\n--{boundary}\r\n`,
		`Content-Disposition: form-data; name="fileContent"; filename="{filename}"\r\n`,
		`Content-Type: {MIME[ext] or "application/octet-stream"}\r\n\r\n`,
		bytes,
		`\r\n--{boundary}--\r\n`,
	})
	return body, `multipart/form-data; boundary={boundary}`
end

local function call(method: string, url: string, key: string, body: string?, contentType: string?): (boolean, any)
	local headers = { ["x-api-key"] = key }
	if contentType then
		headers["content-type"] = contentType
	end
	local ok, res = pcall(net.request, { url = url, method = method :: any, headers = headers, body = body })
	if not ok then
		return false, { message = tostring(res) }
	end
	local okJson, data = pcall(serde.decode, "json", res.body)
	if not res.ok then
		local message = if okJson and type(data) == "table" then (data.message or data.error or res.body) else res.body
		return false, { status = res.statusCode, message = string.sub(tostring(message), 1, 300) }
	end
	return true, if okJson then data else {}
end

local function creatorJson(creator: string): any?
	local kind, id = string.match(creator, "^(%a+):(%d+)$")
	if kind == "user" then
		return { userId = id }
	elseif kind == "group" then
		return { groupId = id }
	end
	return nil
end

-- upload one file and wait for the operation -> asset id or nil, error
local function uploadOne(job: Job, key: string, creator: any): (string?, string?)
	local request = serde.encode("json", {
		assetType = job.assetType,
		displayName = job.name,
		description = UploadPlan.DESCRIPTION,
		creationContext = { creator = creator },
	})
	local body, ctype = multipart(request, job.file, fs.readFile(job.file))
	local ok, res = call("POST", `{API}/assets`, key, body, ctype)
	if not ok then
		return nil, `{res.status or "network"}: {res.message}`
	end
	if res.response and res.response.assetId then
		return tostring(res.response.assetId), nil
	end
	local op = res.path or (res.operationId and `operations/{res.operationId}`)
	if not op then
		return nil, "no operation in the response"
	end
	for _ = 1, 90 do
		task.wait(2)
		local okPoll, poll = call("GET", `{API}/{op}`, key)
		if okPoll and poll.done then
			if poll.response and poll.response.assetId then
				return tostring(poll.response.assetId), nil
			end
			return nil, `rejected: {serde.encode("json", poll.error or poll)}`
		end
	end
	return nil, `timed out waiting for {op}`
end

local function grant(universe: string, assetIds: { string }, key: string): (boolean, string?)
	if #assetIds == 0 then
		return true, nil
	end
	local requests = {}
	for _, id in assetIds do
		table.insert(requests, { assetId = id })
	end
	local body = serde.encode("json", {
		subjectType = "Universe",
		subjectId = universe,
		action = "Use",
		requests = requests,
	})
	local ok, res = call(
		"PATCH",
		"https://apis.roblox.com/asset-permissions-api/v1/assets/permissions",
		key,
		body,
		"application/json"
	)
	return ok, if ok then nil else `{res.status or ""} {res.message}`
end

-- moderation state of uploaded images/audio (public thumbnail endpoint: Pending / Completed / Blocked)
local function moderation(ids: { string }): { [string]: string }
	local out = {}
	for i = 1, #ids, 50 do
		local chunk = table.concat(ids, ",", i, math.min(#ids, i + 49))
		local ok, res = pcall(net.request, {
			url = `https://thumbnails.roblox.com/v1/assets?assetIds={chunk}&size=420x420&format=Png`,
		})
		if ok and res.ok then
			local okJson, data = pcall(serde.decode, "json", res.body)
			if okJson and data.data then
				for _, row in data.data do
					out[tostring(row.targetId)] = row.state
				end
			end
		end
	end
	return out
end

return function(Cli: any)
	Cli.command(
		"kit",
		"moderation",
		'moderation check [<file> ...] | moderation clear <file> "<their words>" --by owner|governor',
		"the moderation gate: screen files for what Roblox moderation could flag (banned words, blood) - kit upload runs it on everything it sends",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local verb = args[1]
			if verb == "clear" then
				local file, words = args[2], args[3]
				if not file or not words then
					return Run.report(
						"moderation",
						{},
						C.USAGE,
						"moderation clear: needs a file and the owner's words",
						'lune run kit moderation clear <file> "<his words>" --by owner'
					)
				end
				local ok, res = Moderation.clear(file, words, tostring(flags.by or ""), Board.now())
				if not ok then
					return Run.report(
						"moderation",
						{},
						C.USAGE,
						`moderation clear: {res}`,
						"only after the owner looked at it"
					)
				end
				Board.journal(Board.agent(flags.as), `moderation: {file} cleared by {flags.by}: "{words}"`)
				return Run.report(
					"moderation",
					{},
					C.PASS,
					`moderation: {file} cleared by {flags.by} (its content {string.sub(res, 1, 12)}: a change holds it again)`,
					"lune run kit upload --dry-run"
				)
			end
			if verb ~= "check" then
				return Run.report(
					"moderation",
					{},
					C.USAGE,
					"moderation: check or clear",
					"lune run kit moderation check <file>"
				)
			end
			local items = {}
			for i = 2, #args do
				table.insert(items, { file = args[i], title = "" })
			end
			if #items == 0 then
				return Run.report(
					"moderation",
					{},
					C.USAGE,
					"moderation check: name the files (kit upload --dry-run screens what it would send)",
					"lune run kit upload --dry-run"
				)
			end
			local verdicts, err = Moderation.screen(items)
			if not verdicts then
				return Run.report(
					"moderation",
					{},
					C.CONTENT,
					`moderation check: could not screen ({err})`,
					"fix the error above"
				)
			end
			local held = 0
			for _, v in verdicts do
				local m = if v.crimson then string.format(" blood-red %.0f%%", v.crimson * 100) else ""
				if v.held then
					held += 1
					print(`[held] {v.file}: {table.concat(v.why, "; ")}`)
				else
					print(`[clean] {v.file}{m}{if v.cleared then " (cleared: " .. v.cleared .. ")" else ""}`)
				end
			end
			if held > 0 then
				return Run.report(
					"moderation",
					{},
					C.CONTENT,
					`moderation check: {held} of {#verdicts} held`,
					"change them (no blood, no gore, nothing moderation could flag); never upload a held file"
				)
			end
			return Run.report("moderation", {}, C.PASS, `moderation check: {#verdicts} clean`, "none - proceed")
		end
	)
	Cli.command(
		"kit",
		"upload",
		"upload [--dry-run] [--status] [--adopt] [--only <text>] [--except <text>[,<text>...]] [--force] [--studio] | upload --record <file> <assetId> | upload --pending",
		"upload every built asset to Roblox and record the ids - no manual uploads, no API key: every file is screened, then the Roblox Studio MCP sends it (open_cloud_invoke with the creator's Studio login) and --record stores its id; with ROBLOX_API_KEY set (headless/CI) the kit sends them itself",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			-- the switches take no value: a word after one is the piece's name, never the switch's value (`upload
			-- --studio sg_holster` read "sg_holster" as --studio's value and sent the WHOLE build into the plan)
			for _, switch in { "studio", "dry-run", "status", "adopt", "force", "pending" } do
				if type(flags[switch]) == "string" then
					table.insert(args, 1, flags[switch])
					flags[switch] = true
				end
			end

			-- THE STUDIO ROUTE, second half: the id open_cloud_invoke returned -> the ledger + the id files
			if flags.record ~= nil then
				local file = if type(flags.record) == "string"
					then UploadPlan.relative(flags.record, process.cwd)
					else nil
				local id = UploadPlan.assetId(args[1])
				if not file or not id then
					return Run.report(
						"upload",
						{},
						C.USAGE,
						"upload --record: needs the file and the asset id open_cloud_invoke returned",
						"lune run parallax upload --record <file> <assetId>   (the files: lune run parallax upload --pending)"
					)
				end
				local plan = readPlan()
				local entry
				for _, e in (if plan then plan.files else {}) :: { any } do
					if e.file == file then
						entry = e
					end
				end
				if not plan or not entry then
					return Run.report(
						"upload",
						{},
						C.USAGE,
						`upload --record: {file} is not in the upload plan ({planPath()})`,
						"lune run parallax upload   (it screens the files and writes the plan first)"
					)
				end
				local now = if fs.isFile(file) then fs.readFile(file) else nil
				if
					not now
					or (
						if entry.sha256
							then serde.hash("sha256", now) ~= entry.sha256
							else Integrity.hash(now) ~= entry.hash
					)
				then
					return Run.report(
						"upload",
						{},
						C.CONTENT,
						`upload --record: {file} changed (or is gone) since the moderation gate screened it - not recorded`,
						"lune run parallax upload   (screens it again and writes a new plan)"
					)
				end
				local recorded = AssetIds.record(file, id)
				local l = ledger()
				l[file] =
					{ id = id, assetType = entry.assetType, hash = entry.hash, at = Board.now(), via = "studio-mcp" }
				saveLedger(l)
				entry.recorded = id
				local left, ids = {}, {}
				for _, e in plan.files :: { any } do
					if e.recorded then
						table.insert(ids, tostring(e.recorded))
					else
						table.insert(left, e)
					end
				end
				savePlan(plan)
				print(`  recorded {file} -> {recorded}`)
				if #left > 0 then
					return Run.report(
						"upload",
						{},
						C.PASS,
						`upload --record: {file} recorded; {#left} file(s) of the plan left`,
						`next: open_cloud_invoke for {left[1].file} (its call is in {planPath()}), then upload --record {left[1].file} <assetId>`
					)
				end
				-- the whole plan is live: new mesh/map ids -> src/models/*.model.json, art ids -> screens
				local modelsStep = Content.modelsCompile(true)
				Content.uiCompile(true)
				Board.journal(Board.agent(flags.as), `kit upload (studio mcp): {#ids} recorded`)
				local up = Config.load().upload or {}
				if up.universe then
					local g = UploadPlan.grant(tostring(up.universe), ids)
					print("  grant them to the experience (so audio plays there):")
					print(
						`    open_cloud_invoke method={g.method} endpoint={g.endpoint} scopes={table.concat(
							g.scopes,
							","
						)}`
					)
					print(`    body={g.body}`)
				end
				return Run.report(
					"upload",
					{},
					C.PASS,
					`upload: all {#ids} file(s) of the plan live and recorded; models: {(modelsStep.result and modelsStep.result.summary) or "refreshed"}`,
					if up.universe
						then `call the grant printed above (open_cloud_invoke; a refused scope is the creator's to grant in Studio's MCP Permissions), then commit assets/ (ids + uploads.json); moderation: lune run parallax upload --status`
						else "commit assets/ (ids + uploads.json); new images/audio need moderation: lune run parallax upload --status"
				)
			end
			if flags.pending then
				local plan = readPlan()
				local left = 0
				for _, e in (if plan then plan.files else {}) :: { any } do
					if not e.recorded then
						left += 1
						print(`  {e.assetType}  {e.file}`)
					end
				end
				return Run.report(
					"upload",
					{},
					C.PASS,
					`upload --pending: {left} file(s) waiting for the Studio MCP`
						.. (if plan then ` (plan {planPath()}, made {plan.made})` else " (no plan)"),
					if left > 0
						then `for each: open_cloud_invoke with its call from {planPath()}, poll the operation, then lune run parallax upload --record <file> <assetId>`
						else "none - proceed"
				)
			end
			-- `kit upload <name>` means --only <name>: a bare name used to be ignored and the WHOLE build went up
			-- (2026-10-27: `kit upload sg_holster_game` started 549 uploads, mostly another lane's sounds)
			if args[1] and flags.only == nil then
				flags.only = args[1]
			end
			local cfg = Config.load()
			local up = cfg.upload or {}
			local l = ledger()

			if flags.status then
				local ids, byId = {}, {}
				for file, entry in l do
					if entry.assetType == "Image" or entry.assetType == "Audio" then
						table.insert(ids, entry.id)
						byId[entry.id] = file
					end
				end
				local states = moderation(ids)
				local pending, blocked = {}, {}
				for id, state in states do
					if state == "Pending" then
						table.insert(pending, byId[id])
					elseif state == "Blocked" then
						table.insert(blocked, byId[id])
					end
				end
				for _, f in pending do
					print("  pending  " .. f)
				end
				for _, f in blocked do
					print("  BLOCKED  " .. f)
				end
				return Run.report(
					"upload",
					{},
					if #blocked > 0 then C.CONTENT else C.PASS,
					`upload status: {#ids} image/audio asset(s) — {#pending} pending moderation, {#blocked} blocked`,
					if #blocked > 0
						then "a blocked asset was rejected by moderation: change it, rebuild, and run lune run kit upload"
						elseif #pending > 0 then "wait (minutes to a few hours), then: lune run kit upload --status"
						else "none — every uploaded image/sound is approved"
				)
			end

			local all = UploadJobs.jobs(cfg.name or "game")
			if flags.adopt then
				-- assets uploaded earlier (by hand, kit asset-id, or a script): record them so they never go up twice
				local ids = if fs.isFile(Config.path("ids"))
					then serde.decode("json", fs.readFile(Config.path("ids")))
					else {}
				local adopted = 0
				for _, job in all do
					local kind, logical = AssetIds.classify(job.file)
					local id = ids[kind] and ids[kind][logical]
					if id == nil then -- older records may sit under another kind (e.g. model maps under "models")
						for _, group in ids do
							if type(group) == "table" and type(group[logical]) == "string" then
								id = group[logical]
								break
							end
						end
					end
					if type(id) == "string" and not l[job.file] then
						l[job.file] = {
							id = string.match(id, "(%d+)$"),
							assetType = job.assetType,
							hash = Integrity.hash(fs.readFile(job.file)),
							at = Board.now(),
							adopted = true,
						}
						adopted += 1
					end
				end
				saveLedger(l)
				return Run.report(
					"upload",
					{},
					C.PASS,
					`upload: adopted {adopted} already-uploaded file(s) into {LEDGER}`,
					"lune run kit upload --dry-run   (shows what is still missing)"
				)
			end
			local todo: { Job } = {}
			for _, job in all do
				-- filter BEFORE reading: --only must not hash (or trip on) every other lane's files, and a listed file
				-- that is gone (an animation export that failed) is skipped, not a crash
				local wanted = not flags.only or string.find(job.file, flags.only, 1, true) ~= nil
				-- --except a,b: those files stay out of THIS batch (a file the moderation gate held keeps its last
				-- uploaded id until it is changed or the owner clears it); everything sent is still screened
				if wanted and type(flags.except) == "string" then
					for _, word in string.split(flags.except, ",") do
						if word ~= "" and string.find(job.file, word, 1, true) then
							wanted = false
						end
					end
				end
				if wanted and fs.isFile(job.file) then
					local entry = l[job.file]
					local hash = Integrity.hash(fs.readFile(job.file))
					if flags.force or not entry or entry.hash ~= hash then
						table.insert(todo, job)
					end
				end
			end
			-- THE MODERATION GATE (kit/lib/moderation.luau: blood and gore get the uploading account moderated): every file about to leave is screened -
			-- its name and title for banned words, every image for blood - and a held file stops the WHOLE upload
			-- before any key is read. The screening is logged first, held or clean.
			local items = {}
			for _, job in todo do
				table.insert(items, { file = job.file, title = job.name })
			end
			local verdicts, gateErr = Moderation.screen(items)
			if not verdicts then
				return Run.report(
					"upload",
					{},
					C.CONTENT,
					`upload: the moderation gate could not screen the files - nothing sent ({gateErr})`,
					"fix the gate's error (python -I kit/tools/mod_gate.py <png> runs the image check alone)"
				)
			end
			local logPath = Moderation.log(verdicts, Board.now())
			local held = {}
			for _, v in verdicts do
				if v.held then
					table.insert(held, v)
					print(`  HELD  {v.file}: {table.concat(v.why, "; ")}`)
				elseif v.cleared then
					print(`  cleared  {v.file} ({v.cleared})`)
				end
			end
			if flags["dry-run"] then
				for _, job in todo do
					print(`  {job.assetType}  {job.file}`)
				end
				if #held > 0 then
					return Run.report(
						"upload",
						{},
						C.CONTENT,
						`upload (dry run): {#todo} of {#all} file(s) are new or changed; {#held} HELD by the moderation gate - first: {held[1].file} ({table.concat(
							held[1].why,
							"; "
						)})`,
						`change it (no blood, no gore, nothing moderation could flag) or have the owner clear it after looking: lune run kit moderation clear {held[1].file} "<his words>" --by owner`
					)
				end
				return Run.report(
					"upload",
					{},
					C.PASS,
					`upload (dry run): {#todo} of {#all} file(s) are new or changed`,
					"lune run kit upload"
				)
			end
			if #todo == 0 then
				return Run.report(
					"upload",
					{},
					C.PASS,
					`upload: all {#all} built file(s) are already live`,
					"lune run kit upload --status   (moderation)"
				)
			end
			if #held > 0 then
				return Run.report(
					"upload",
					{},
					C.CONTENT,
					`upload: NOTHING sent - {#held} file(s) held by the moderation gate (log: {logPath}) - first: {held[1].file} ({table.concat(
						held[1].why,
						"; "
					)})`,
					`change it (no blood, no gore, nothing moderation could flag) or have the owner clear it after looking: lune run kit moderation clear {held[1].file} "<his words>" --by owner`
				)
			end
			local creator = creatorJson(tostring(up.creator or ""))
			if not creator then
				return Run.report(
					"upload",
					{},
					C.USAGE,
					'upload: kit.config.json needs "upload": {"creator": "user:<your user id>"} (or "group:<id>")',
					'add it (user id = the number in your roblox.com profile URL); optional "universe": <experience id> grants audio to it'
				)
			end
			-- headless (CI, no Studio): a key in the environment only, read here and never printed or written
			local key = process.env.ROBLOX_API_KEY
			if (not key or key == "") and process.os == "windows" then
				-- (`setx` only reaches NEW terminals: read the user's saved value directly)
				local ok, res = pcall(process.exec, "reg", { "query", "HKCU\\Environment", "/v", "ROBLOX_API_KEY" })
				if ok and res.ok then
					key = string.match(res.stdout, "ROBLOX_API_KEY%s+REG_%w+%s+(%S+)")
				end
			end
			if not key or key == "" or flags.studio then
				-- THE STUDIO ROUTE (no key): the plan of exact open_cloud_invoke calls; the agent sends, --record keeps
				local files, tooBig = {}, {}
				for _, job in todo do
					local bytes = fs.readFile(job.file)
					if #bytes > UploadPlan.MAX_BYTES then
						table.insert(tooBig, `{job.file} ({math.floor(#bytes / 1048576)} MB)`)
					end
					table.insert(files, {
						file = job.file,
						assetType = job.assetType,
						name = job.name,
						hash = Integrity.hash(bytes), -- (the ledger's own hash, as the key route writes it)
						-- what --record checks: the file's bytes as the moderation gate screened them (SHA-256)
						sha256 = serde.hash("sha256", bytes),
						call = UploadPlan.call(job, creator, process.cwd),
					})
				end
				if #tooBig > 0 then
					return Run.report(
						"upload",
						{},
						C.CONTENT,
						`upload: {#tooBig} file(s) over the Studio MCP's 20 MB limit - first: {tooBig[1]}`,
						"make them smaller (texture size, mesh split) and run lune run parallax upload again"
					)
				end
				savePlan({
					made = Board.now(),
					how = "For each entry of files: call the Roblox Studio MCP tool open_cloud_invoke with entry.call "
						.. "(method, endpoint, body verbatim, files, scopes; studio_id from list_roblox_studios). It "
						.. "returns an operation: poll open_cloud_invoke GET /assets/v1/operations/<operationId> until "
						.. "done is true; the asset id is response.assetId. Then run: lune run parallax upload --record "
						.. "<entry.file> <assetId>. Studio must have a place of a PUBLISHED game open (permissions are "
						.. "kept per game). A refused file or scope: the creator approves this project's build folder "
						.. "and the asset:read + asset:write scopes in Studio (the MCP button, bottom right -> MCP "
						.. "Permissions) - never work around it. Uploads are permanent.",
					creator = up.creator,
					universe = up.universe,
					files = files,
				})
				for _, f in files do
					print(`  {f.assetType}  {f.file}`)
				end
				local first = files[1].call
				print("")
				print("  the first call (every file's is in the plan):")
				print(
					`    open_cloud_invoke method={first.method} endpoint={first.endpoint} scopes={table.concat(
						first.scopes,
						","
					)}`
				)
				print(`    body={first.body}`)
				print(`    files=[name: fileContent, path: {first.files[1].path}]`)
				return Run.report(
					"upload",
					{},
					C.PASS,
					`upload: {#files} file(s) screened and ready for the Roblox Studio MCP (no API key) - plan {planPath()}`,
					`for each file in the plan: open_cloud_invoke with its call (studio_id from list_roblox_studios), poll GET /assets/v1/operations/<operationId> until done, then lune run parallax upload --record <file> <assetId>`
				)
			end
			local okCount, failed, newIds = 0, {}, {}
			for i, job in todo do
				stdio.write(`[{i}/{#todo}] {job.assetType} {job.file} ... `)
				local id, problem = uploadOne(job, key, creator)
				if id then
					local recorded = AssetIds.record(job.file, id)
					l[job.file] = {
						id = id,
						assetType = job.assetType,
						hash = Integrity.hash(fs.readFile(job.file)),
						at = Board.now(),
					}
					saveLedger(l) -- after every success: an interrupted run never loses what went up
					table.insert(newIds, id)
					okCount += 1
					print(`ok {recorded}`)
				else
					table.insert(failed, `{job.file}: {problem}`)
					print(`FAILED {problem}`)
				end
			end
			local granted = ""
			if up.universe and #newIds > 0 then
				local ok, problem = grant(tostring(up.universe), newIds, key)
				granted = if ok
					then `, granted to experience {up.universe}`
					else ` (grant to {up.universe} FAILED: {problem} — does the key have asset-permissions write?)`
			end
			-- new mesh/map ids -> src/models/*.model.json, so Models.spawn has them without another command
			local modelsStep = Content.modelsCompile(true)
			Content.uiCompile(true) -- art ids -> screens (the "art:<name>" images resolve now)
			granted ..= `; models: {(modelsStep.result and modelsStep.result.summary) or "refreshed"}`
			Board.journal(Board.agent(flags.as), `kit upload: {okCount} uploaded, {#failed} failed`)
			if #failed > 0 then
				return Run.report(
					"upload",
					{},
					C.CONTENT,
					`upload: {okCount} ok, {#failed} failed{granted} — first: {failed[1]}`,
					"fix the cause above and re-run: lune run kit upload (only what is missing goes up)"
				)
			end
			return Run.report(
				"upload",
				{},
				C.PASS,
				`upload: {okCount} file(s) live and recorded{granted}`,
				"commit assets/ (ids + uploads.json); new images/audio need moderation: lune run kit upload --status"
			)
		end
	)
end

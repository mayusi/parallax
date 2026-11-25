-- review.luau — `kit review <name>`: ONE page for one piece, the owner's approvals in one place (the 3D studio-route
-- plan, H8; wave 2 of the pipelines plan he approved 2026-11-12). Why: he approved by telling a session, and what he
-- was asked to look at were files in folders. The page shows the piece's stages in the order they are made
-- (kit/lib/review.luau: a model sheet, a blockout, a beat chart, a style sheet, the newest build's views, the
-- dailies, the finished piece), each with its state, its pictures, a note box and what he may do there: Approve,
-- Redo, a verdict.
--
-- A click writes nothing by itself: it is turned into the kit's own command (Review.plan) and run here, in this
-- process - `kit approve ... --by owner --stage`, `kit vfx chart ... --approve`, `kit verdict`, `kit task rework` -
-- so the record is the one a typed command writes, and every refusal of those commands is the page's too.
--   * An approval or a verdict is for what he SAW: the click names what the page showed ("seen"), and is refused
--     when the sheet was redrawn or the chart re-timed in the meantime (the page then shows the new one). The
--     command is told the same (--expect, --expect-plan) and reads the artefact itself once more: what changed
--     between the page's look and the command's is refused there. "What he saw" is the PICTURES where the artefact
--     names them (a style sheet's "drawn", a chart picture's plan), not only what they were made from.
--   * The page and its commands read ONE folder: a chart is approved in the folder the page read it in
--     (--measured), an effect's sheet in the effects folder the page read (--effects).
--   * One click at a time: a second one while a command runs is asked to wait.
--   * Local only: it listens on 127.0.0.1; every answer but the page itself needs the page's own token
--     (kit/lib/localpage.luau), a picture is served only when a stage names it, and the page is never shown inside
--     another page's frame (a framed page would pass every other check: the click would be his, on what he cannot see).
--   kit review <name> [--lane 3d|vfx|anim|world] [--port 8791] [--no-open]      (the piece is the active project's)
--   kit review <name> --dry        try the page: every click answers with the command it WOULD run, nothing is recorded
--   kit review <name> --stages     no page: the stages and their states as lines (what a session reads)
--   (not --list: Cli.parse keeps repeated flags in flags.list, so a flag of that name is always "set")
--   (a FIXTURE project's piece: --models <its models folder> or --effects <its effects folder>, with --locks
--    <its own locks file> - always both, and never the project's own record under another spelling: Locks.useFixture)
local fs = require("@lune/fs")
local net = require("@lune/net")
local process = require("@lune/process")
local serde = require("@lune/serde")
local task = require("@lune/task")

local LocalPage = require("../lib/localpage")
local Locks = require("../lib/locks")
local Review = require("../lib/review")
local Run = require("../lib/run")

local C = Run.CODES
local PAGE = "kit/review/index.html"
local HEADER = "x-review-token"
-- (mp4: a stage's video - the timing animatic beside its scene; served whole, a few MB)
local TYPES = { png = "image/png", jpg = "image/jpeg", jpeg = "image/jpeg", gif = "image/gif", mp4 = "video/mp4" }

local function json(status: number, data: any): any
	return {
		status = status,
		headers = { ["Content-Type"] = "application/json; charset=utf-8", ["Cache-Control"] = "no-store" },
		body = serde.encode("json", data),
	}
end

-- run one of the kit's own commands in this process and keep what it said (its summary / next_action lines)
local function runKit(Cli: any, command: string, args: { string }): (boolean, string, string)
	local said: { string } = {}
	local out = Run.out
	Run.out = function(line: string)
		table.insert(said, line)
		out(line)
	end
	-- the command reads the locks file as it is on disk NOW: the page's own read may be seconds old, and another
	-- session's record written since must not be saved over
	Locks.reset()
	local ok, code = pcall(Cli.run, command, args)
	Run.out = out
	local summary, next = "", ""
	for _, line in said do
		summary = string.match(line, "^summary: (.*)$") or summary
		next = string.match(line, "^next_action: (.*)$") or next
	end
	if not ok then
		return false, `the command crashed: {tostring(code)}`, ""
	end
	return code == C.PASS, summary, next
end

local function handler(Cli: any, secret: string, port: number, piece: any)
	local shown: { Review.Stage } = {}
	local allowed: { [string]: boolean } = {}
	local busy = false -- one click's command at a time (runKit swaps Run.out for its length)
	local function read(): { Review.Stage }
		Locks.reset() -- (a session's typed approval is seen at the next look)
		shown = Review.stages(piece.lane, piece.name, piece.opts)
		allowed = Review.allowed(shown)
		return shown
	end
	-- what changes when the page should be drawn again: the locks file, every picture it shows, and every place a
	-- picture it does not show YET would appear (Review.watch)
	local function stamp(): string
		local parts = { Review.modified(Locks.FILE) }
		for _, path in Review.watch(piece.lane, piece.name, piece.opts) do
			table.insert(parts, Review.modified(path))
		end
		for _, s in shown do
			table.insert(parts, `{s.key}={s.state}`)
			for _, p in s.pictures do
				table.insert(parts, Review.modified(p.path))
			end
		end
		return table.concat(parts, ",")
	end
	read()
	return function(req: any): any
		if not LocalPage.hostOk(req.headers, port) then
			return json(403, { error = "forbidden host" })
		end
		local q = req.query or {}
		if req.method == "GET" and (req.path == "/" or req.path == "/index.html") then
			if not fs.isFile(PAGE) then
				return { status = 500, body = `{PAGE} is missing (kit install / kit sync restores it)` }
			end
			if LocalPage.framed(req.headers) then
				return { status = 403, body = "this page is not shown inside another page: open it in its own tab" }
			end
			return {
				status = 200,
				-- nothing from anywhere else is loaded or called by this page (its own inline script and style, its
				-- own pictures, its own /api), and it is never shown in another page's frame (LocalPage.pageHeaders)
				headers = LocalPage.pageHeaders(
					"default-src 'self'; img-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'"
				),
				body = (string.gsub(fs.readFile(PAGE), "__REVIEW_TOKEN__", secret)),
			}
		elseif req.method == "GET" and req.path == "/file" then
			local p = tostring(q.p or "")
			local ext = string.match(string.lower(p), "%.(%w+)$")
			-- the page's own token (an <img> cannot send a header: it is in the address), and only a picture a
			-- stage names right now: never a path the page (or anyone) made up
			if q.k ~= secret or not allowed[p] or not ext or not TYPES[ext] or not fs.isFile(p) then
				return { status = 404, body = "not found" }
			end
			-- a part of the file when the browser asks for one (a video is scrubbed, and on some browsers only
			-- played at all, through Range requests)
			local data = fs.readFile(p)
			local part = LocalPage.range(req.headers.range, #data)
			local headers = {
				["Content-Type"] = TYPES[ext],
				["Cache-Control"] = "no-store",
				["Accept-Ranges"] = "bytes",
			}
			if part.status == 416 then
				headers["Content-Range"] = `bytes */{#data}`
				return { status = 416, headers = headers, body = "" }
			elseif part.status == 206 then
				headers["Content-Range"] = `bytes {part.first}-{part.last}/{#data}`
				return { status = 206, headers = headers, body = string.sub(data, part.first + 1, part.last + 1) }
			end
			return { status = 200, headers = headers, body = data }
		end
		-- everything else is the page's own: nothing is told, and nothing is made to run, for anyone without its token
		if req.headers[HEADER] ~= secret then
			return json(403, { error = "missing or wrong page token (reload the page)" })
		end
		if req.method == "GET" and req.path == "/api/review" then
			local stages = read()
			local answer = json(200, {
				name = piece.name,
				lane = piece.lane,
				dry = piece.dry,
				note = Review.note(piece.lane, piece.name, stages, piece.opts),
				stages = stages,
				stamp = stamp(),
			})
			-- an empty Lua table is written as {}: a stage with no pictures / nothing to do must still answer a LIST
			answer.body = string.gsub(answer.body, '"actions":{}', '"actions":[]')
			answer.body = string.gsub(answer.body, '"pictures":{}', '"pictures":[]')
			return answer
		elseif req.method == "GET" and req.path == "/api/stamp" then
			return json(200, { stamp = stamp() })
		elseif req.method == "POST" and req.path == "/api/act" then
			local why = LocalPage.writeProblem(req.headers, port, secret, HEADER)
			if why then
				return json(403, { error = why })
			end
			local ok, body = pcall(serde.decode, "json" :: any, req.body or "")
			if not ok or type(body) ~= "table" then
				return json(400, { error = "the body is not JSON" })
			end
			if busy then
				return json(
					409,
					{ ok = false, message = "another click is still being recorded: wait a moment and click again" }
				)
			end
			busy = true
			local done, answer = pcall(function(): any
				local stage: Review.Stage? = nil
				for _, s in read() do
					if s.key == body.stage then
						stage = s
					end
				end
				if not stage then
					return json(404, { error = `no stage "{tostring(body.stage)}"` })
				end
				local action = tostring(body.action)
				local opts = {
					models = if piece.opts then piece.opts.models else nil,
					effects = if piece.opts then piece.opts.effects else nil,
					route = body.route,
				}
				local command, args = Review.plan(piece.lane, piece.name, stage, action, body.words, body.score, opts)
				if not command then
					return json(400, { ok = false, message = args })
				end
				if not Review.fresh(stage, action, body.seen) then
					return json(409, {
						ok = false,
						stale = true,
						message = `{stage.title} changed while you were looking: the page now shows it as it is. Look again, then click.`,
					})
				end
				local typed = Review.typed(command, args)
				if piece.dry then
					print(`review (dry): {typed}`)
					return json(
						200,
						{ ok = true, dry = true, message = `DRY RUN - nothing recorded. It would run: {typed}` }
					)
				end
				local good, summary, next = runKit(Cli, command, args)
				print(`review: {typed} -> {if good then "ok" else "refused"}`)
				read()
				return json(if good then 200 else 400, { ok = good, message = summary, next = next, ran = typed })
			end)
			busy = false
			if not done then
				return json(500, { ok = false, message = `the page's server failed: {tostring(answer)}` })
			end
			return answer
		end
		return json(404, { error = "not found" })
	end
end

return function(Cli: any)
	Cli.command(
		"work",
		"review",
		"review <name> [--lane 3d|vfx|anim|world] [--port 8791] [--no-open] [--dry] | review <name> --stages",
		"ONE page for one piece of the active project: its stages in order (model sheet, blockout, beat chart, style sheet, the newest build's views, dailies, the finished piece), each with its state, its pictures, a note box and Approve / Redo / a verdict; a click runs the kit's own command (kit approve --stage, kit verdict, kit task rework) for what the page showed, so the record is the one the locks read. --dry records nothing; --stages prints the stages for a session",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local name = args[1]
			if not name then
				return Run.report(
					"review",
					{},
					C.USAGE,
					"review: name the piece",
					"lune run kit review <name> [--lane 3d|vfx|anim|world]"
				)
			end
			-- a fixture project's piece: its own folder (--models: a 3D piece, --effects: an effect) AND its own locks
			-- file, never one without the other (a click must not write another folder's sheet id into the project's
			-- own record)
			local models = if type(flags.models) == "string" then flags.models else nil
			local effects = if type(flags.effects) == "string" then flags.effects else nil
			local locks = if type(flags.locks) == "string" then flags.locks else nil
			if (models == nil and effects == nil) ~= (locks == nil) then
				return Run.report(
					"review",
					{},
					C.USAGE,
					"review: --models and --locks go together (a fixture project's piece is recorded in its own locks file; --effects the same)",
					"lune run kit review <name> (a real piece needs neither)"
				)
			end
			if locks then
				local why = Locks.useFixture(locks)
				if why then
					return Run.report(
						"review",
						{},
						C.USAGE,
						`review: {why}`,
						"lune run kit review <name> (a real piece needs neither --models nor --locks)"
					)
				end
			end
			local lane = if type(flags.lane) == "string"
				then flags.lane
				else (if models then "3d" elseif effects then "vfx" else Review.laneOf(name))
			if not lane or not table.find(Review.LANES, lane) then
				return Run.report(
					"review",
					{},
					C.USAGE,
					`review: no piece "{name}" in the active project's 3D, VFX, animation or world lane (another game's: --game <Name>; or an unknown --lane)`,
					"lune run kit review <name> --lane 3d|vfx|anim|world"
				)
			end
			local opts = { models = models, effects = effects }
			local stages = Review.stages(lane :: string, name, opts)
			-- (a flag given a value - "--stages 1", "--dry yes" - is still that flag: --dry must never be lost)
			if flags.stages ~= nil then
				local waiting = 0
				for i, s in stages do
					print(`  {i}. {Review.line(s)}`)
					if s.state == "waiting" or s.state == "changed" then
						waiting += 1
					end
				end
				local note = Review.note(lane :: string, name, stages, opts)
				if note then
					print(`  note: {note}`)
				end
				return Run.report(
					"review",
					{},
					C.PASS,
					`review {lane}/{name}: {#stages} stage(s), {waiting} waiting for the owner`,
					if waiting > 0
						then `show the owner the page: lune run kit review {name} --lane {lane} (his notes land on the board: lune run kit task resume)`
						else "nothing waits for the owner on this piece"
				)
			end
			local port = tonumber(flags.port) or Review.PORT
			local secret = LocalPage.token()
			local piece = { name = name, lane = lane, opts = opts, dry = flags.dry ~= nil }
			local ok, err = pcall(
				net.serve,
				port,
				{ address = "http://127.0.0.1", handleRequest = handler(Cli, secret, port, piece) }
			)
			if not ok then
				return Run.report(
					"review",
					{},
					C.USAGE,
					`review: could not listen on 127.0.0.1:{port} ({err})`,
					`lune run kit review {name} --port <another port>`
				)
			end
			local url = `http://127.0.0.1:{port}/`
			print(
				`review: {url}   ({lane}/{name}, {#stages} stage(s){if piece.dry
					then ", DRY RUN: nothing is recorded"
					else ""}; Ctrl+C stops it)`
			)
			print(`summary: review page serving at {url}`)
			print(
				"next_action: open it in the browser; a click runs the kit's own command; leave this running while he looks"
			)
			if not flags["no-open"] then
				if process.os == "windows" then
					pcall(process.exec, "cmd", { "/c", "start", "", url })
				elseif process.os == "macos" then
					pcall(process.exec, "open", { url })
				else
					pcall(process.exec, "xdg-open", { url })
				end
			end
			while true do
				task.wait(3600)
			end
		end
	)
end

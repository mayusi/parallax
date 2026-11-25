-- board.luau — `kit board`: the project's own Trello, local (the owner, 2026-10-28: "we're not going to use Trello.
-- We're going to make our own ... even better"). A page on 127.0.0.1 over the SAME markdown task files the CLI and every
-- model write (kit/lib/boardweb.luau): every board (the project and each game), columns by status, drag a card to move
-- it, tick its done-when items, add notes and cards; each card shows its claim (stale ones flagged), what it waits on
-- and the pipeline pieces it names with their preview and the owner's last verdict. A model's change to a task file
-- shows up within seconds. Nothing leaves the machine: it listens on 127.0.0.1 only, writes need the page's own token.
--   kit board [--port 8790] [--no-open]      serve it (Ctrl+C stops); opens the active game's board in the browser
--   kit board stop                           end the background one kit start / kit game use started
-- kit start and kit game use start it hidden when nothing answers on 8790 (off: KIT_NO_BOARD=1 or "board_auto": false)
local fs = require("@lune/fs")
local net = require("@lune/net")
local process = require("@lune/process")
local serde = require("@lune/serde")
local task = require("@lune/task")

local BoardWeb = require("../lib/boardweb")
local Config = require("../lib/config")
local LocalPage = require("../lib/localpage")
local Run = require("../lib/run")

local PAGE = "kit/board/index.html"
local PREVIEW = "^[%w_/%-]*build/renders/[%w_%-%.]+%.png$" -- the only files the page may fetch

-- the page's write token: from the OS's CSPRNG (python's secrets); the hash fallback only when python is missing
local function token(): string
	local ok, r = pcall(process.exec, Run.tool("python"), { "-c", "import secrets; print(secrets.token_hex(24))" })
	if ok and r.ok and string.match(r.stdout, "^%x+%s*$") then
		return (string.gsub(r.stdout, "%s+", ""))
	end
	local seed = `{os.time()}|{os.clock()}|{tostring({})}|{math.random()}`
	local out = {}
	for round = 1, 4 do
		local h = 2166136261 + round
		for i = 1, #seed do
			h = bit32.bxor(h, string.byte(seed, i))
			h = (h * 16777619) % 4294967296
		end
		table.insert(out, string.format("%08x", h))
		seed ..= out[#out]
	end
	return table.concat(out)
end

local function json(status: number, data: any): any
	return {
		status = status,
		headers = { ["Content-Type"] = "application/json; charset=utf-8", ["Cache-Control"] = "no-store" },
		body = serde.encode("json", data),
	}
end

-- the page's board summaries: name + how many cards in each column
local function summaries(): { any }
	local out = {}
	for _, b in BoardWeb.boards() do
		local counts = {}
		for _, t in BoardWeb.tasks(b) do
			counts[t.status] = (counts[t.status] or 0) + 1
		end
		table.insert(out, { key = b.key, name = b.name, counts = counts })
	end
	return out
end

-- every board's cards together (the "all games" view): each card tagged with its board
local function readAll(): any
	local cards, stamps = {}, {}
	for _, b in BoardWeb.boards() do
		local r = BoardWeb.read(b)
		for _, c in r.tasks do
			c.board = b.key
			c.boardName = b.name
			table.insert(cards, c)
		end
		table.insert(stamps, r.stamp)
	end
	return { key = "all", name = "All boards", stamp = table.concat(stamps, ","), tasks = cards }
end

local function stampOf(key: string): string?
	if key == "all" then
		local s = {}
		for _, b in BoardWeb.boards() do
			table.insert(s, BoardWeb.stamp(b))
		end
		return table.concat(s, ",")
	end
	local b = BoardWeb.board(key)
	return if b then BoardWeb.stamp(b) else nil
end

local function handler(secret: string, port: number)
	-- DNS rebinding: only a page loaded from this machine by its own name and port talks to the board (an exact
	-- match: a prefix test would let 127.0.0.1.evil.example through). The bare names too: lune's own client (kit start
	-- asking whether the board is up) sends no port, and a browser always sends the name + port it loaded
	local hosts = {
		[`127.0.0.1:{port}`] = true,
		[`localhost:{port}`] = true,
		["127.0.0.1"] = true,
		["localhost"] = true,
	}
	local origins = { [`http://127.0.0.1:{port}`] = true, [`http://localhost:{port}`] = true }
	return function(req: any): any
		local host = string.lower(tostring(req.headers.host or ""))
		if not hosts[host] then
			return json(403, { error = "forbidden host" })
		end
		local q = req.query or {}
		if req.method == "GET" and (req.path == "/" or req.path == "/index.html") then
			if not fs.isFile(PAGE) then
				return { status = 500, body = `{PAGE} is missing (kit install / kit sync restores it)` }
			end
			-- the page carries its write token: never shown inside another page's frame (clickjacking), the same
			-- headers as kit review's page (LocalPage; the V3 list's kit hygiene: "add LocalPage.pageHeaders in kit board")
			if LocalPage.framed(req.headers) then
				return { status = 403, body = "the board is not shown inside another page" }
			end
			local html = string.gsub(fs.readFile(PAGE), "__BOARD_TOKEN__", secret)
			return { status = 200, headers = LocalPage.pageHeaders(), body = html }
		elseif req.method == "GET" and req.path == "/api/boards" then
			local active = Config.game()
			return json(200, { boards = summaries(), active = if active then active else "root" })
		elseif req.method == "GET" and req.path == "/api/board" then
			if q.key == "all" then
				return json(200, readAll())
			end
			local b = BoardWeb.board(q.key)
			if not b then
				return json(404, { error = "no such board" })
			end
			return json(200, BoardWeb.read(b))
		elseif req.method == "GET" and req.path == "/api/stamp" then
			local s = stampOf(tostring(q.key or ""))
			return if s then json(200, { stamp = s }) else json(404, { error = "no such board" })
		elseif req.method == "GET" and req.path == "/file" then
			local p = tostring(q.p or "")
			if not string.match(p, PREVIEW) or string.find(p, "..", 1, true) or not fs.isFile(p) then
				return { status = 404, body = "not found" }
			end
			return {
				status = 200,
				headers = { ["Content-Type"] = "image/png", ["Cache-Control"] = "no-store" },
				body = fs.readFile(p),
			}
		elseif req.method == "POST" and req.path == "/api/act" then
			-- a custom header no other site can send without a CORS preflight this server never grants
			if req.headers["x-board-token"] ~= secret then
				return json(403, { error = "missing or wrong board token (reload the page)" })
			end
			-- and from this page only: a browser always names the page that sent a write
			local origin, site = req.headers.origin, req.headers["sec-fetch-site"]
			if
				(origin and not origins[string.lower(origin)]) or (site and site ~= "same-origin" and site ~= "none")
			then
				return json(403, { error = "writes come from the board page only" })
			end
			local b = BoardWeb.board(q.key)
			if not b then
				return json(404, { error = "no such board" })
			end
			local ok, body = pcall(serde.decode, "json" :: any, req.body or "")
			if not ok then
				return json(400, { error = "the body is not JSON" })
			end
			local done, message, id = BoardWeb.act(b, body)
			if done then
				print(`board: {b.name} {message}`)
			end
			return json(if done then 200 else 400, { ok = done, message = message, id = id })
		end
		return json(404, { error = "not found" })
	end
end

return function(Cli: any)
	Cli.command(
		"work",
		"board",
		"board [--port 8790] [--no-open] | board stop",
		"the project's own Trello, local: every board (the project + each game) as columns by status over the same task files the CLI writes; drag cards, tick done-when items, add notes and cards; each card shows its claim (stale flagged), what it waits on and the pipeline pieces it names with preview + the owner's last verdict",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			if args[1] == "stop" then
				local ok, msg = BoardWeb.stop()
				return Run.report(
					"board",
					{},
					if ok then Run.CODES.PASS else Run.CODES.USAGE,
					`board: {msg}`,
					if ok then "none" else "lune run kit board (to serve one)"
				)
			end
			local port = tonumber(flags.port) or BoardWeb.PORT
			if #BoardWeb.boards() == 0 then
				return Run.report(
					"board",
					{},
					Run.CODES.USAGE,
					"board: no board here (no board/tasks/, no games/<Name>/board/)",
					'lune run kit task add "the first task"'
				)
			end
			local secret = token()
			local ok, err =
				pcall(net.serve, port, { address = "http://127.0.0.1", handleRequest = handler(secret, port) })
			if not ok then
				return Run.report(
					"board",
					{},
					Run.CODES.USAGE,
					`board: could not listen on 127.0.0.1:{port} ({err})`,
					"lune run kit board --port <another port>"
				)
			end
			local active = Config.game()
			local url = `http://127.0.0.1:{port}/` .. (if active then `?board={active}` else "")
			print(`board: {url}   ({#BoardWeb.boards()} board(s); Ctrl+C stops it)`)
			print(`summary: board serving at {url}`)
			print("next_action: open it in the browser; leave this running while you work")
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

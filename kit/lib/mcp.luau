-- mcp.luau — the kit talks to Roblox Studio itself: a minimal MCP client over stdio to Roblox's own StudioMCP.exe
-- (shipped with Studio; the same server any agent harness uses). JSON-RPC 2.0, one message per line.
--   local Mcp = require("./mcp")
--   local studio, err = Mcp.connect()            -- spawns StudioMCP.exe, initializes
--   local ok, text = studio:call("list_roblox_studios", {}, 20)
--   studio:close()
-- Every call has a timeout: the child's stdout is read by a background task, so a silent Studio never hangs the kit.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local task = require("@lune/task")

local Mcp = {}

-- StudioMCP.exe: KIT_STUDIO_MCP, else the newest Studio version folder that has it
function Mcp.exe(): string?
	local forced = process.env.PARALLAX_STUDIO_MCP or process.env.KIT_STUDIO_MCP
	if forced and forced ~= "" and fs.isFile(forced) then
		return forced
	end
	local base = (process.env.LOCALAPPDATA or "") .. "/Roblox/Versions"
	if not fs.isDir(base) then
		return nil
	end
	local best, bestTime = nil, -1
	for _, v in fs.readDir(base) do
		local p = `{base}/{v}/StudioMCP.exe`
		if fs.isFile(p) then
			local ok, meta = pcall(fs.metadata, p)
			local t = if ok and meta.modifiedAt then meta.modifiedAt.unixTimestamp else 0
			if t > bestTime then
				best, bestTime = p, t
			end
		end
	end
	return best
end

export type Client = {
	call: (self: Client, tool: string, args: { [string]: any }, timeout: number?) -> (boolean, string),
	close: (self: Client) -> (),
}

function Mcp.connect(): (Client?, string?)
	local exe = Mcp.exe()
	if not exe then
		return nil, "no StudioMCP.exe (install Roblox Studio, or set KIT_STUDIO_MCP)"
	end
	local ok, child = pcall(process.create, exe, {})
	if not ok then
		return nil, `could not start {exe}: {child}`
	end
	local buffer, closed = "", false
	task.spawn(function()
		while true do
			local chunk = child.stdout:read()
			if not chunk then
				closed = true
				break
			end
			buffer ..= chunk
		end
	end)
	local nextId = 0

	local function send(msg: { [string]: any })
		child.stdin:write(serde.encode("json", msg) .. "\n")
	end

	-- the next message with this id (notifications in between are skipped)
	local function await(id: number, timeout: number): any?
		local t0 = os.clock()
		while os.clock() - t0 < timeout do
			local nl = string.find(buffer, "\n", 1, true)
			if nl then
				local line = string.sub(buffer, 1, nl - 1)
				buffer = string.sub(buffer, nl + 1)
				local okD, msg = pcall(serde.decode, "json" :: any, line)
				if okD and type(msg) == "table" and msg.id == id then
					return msg
				end
			elseif closed then
				return nil
			else
				task.wait(0.05)
			end
		end
		return nil
	end

	local function request(method: string, params: any, timeout: number): any?
		nextId += 1
		send({ jsonrpc = "2.0", id = nextId, method = method, params = params })
		return await(nextId, timeout)
	end

	local init = request("initialize", {
		protocolVersion = "2024-11-05",
		capabilities = {},
		clientInfo = { name = "roblox-kit", version = "1" },
	}, 20)
	if not init or not init.result then
		pcall(function()
			child:kill()
		end)
		return nil, "StudioMCP.exe did not answer initialize"
	end
	send({ jsonrpc = "2.0", method = "notifications/initialized" })

	local client = {}
	function client.call(_self: any, tool: string, args: { [string]: any }, timeout: number?): (boolean, string)
		local msg = request("tools/call", { name = tool, arguments = args }, timeout or 60)
		if not msg then
			return false, `{tool}: no answer in {timeout or 60} s`
		end
		if msg.error then
			return false, `{tool}: {msg.error.message or serde.encode("json", msg.error)}`
		end
		local parts = {}
		for _, c in (msg.result and msg.result.content) or {} do
			if c.type == "text" and type(c.text) == "string" then
				table.insert(parts, c.text)
			end
		end
		return not (msg.result and msg.result.isError), table.concat(parts, "\n")
	end
	function client.close(_self: any)
		pcall(function()
			child:kill()
		end)
	end
	return (client :: any) :: Client, nil
end

-- console text -> (errors, warnings): the lines a playtest fails on, with their file:line when the line has one
function Mcp.consoleProblems(text: string): ({ string }, { string })
	local errors, warnings = {}, {}
	for line in string.gmatch(text .. "\n", "([^\n]*)\n") do
		local low = string.lower(line)
		if
			string.find(low, "error", 1, true)
			or string.find(low, "attempt to", 1, true)
			or string.find(low, "stack begin", 1, true)
			or string.find(low, "exception", 1, true)
		then
			table.insert(errors, line)
		elseif string.find(low, "warn", 1, true) or string.find(line, "%[W%]") then
			table.insert(warnings, line)
		end
	end
	return errors, warnings
end

return Mcp

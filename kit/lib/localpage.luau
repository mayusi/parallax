-- localpage.luau (kit) — what a page the kit serves on 127.0.0.1 needs before it may WRITE anything (the rules
-- kit/cmd/board.luau set, 2026-10-28, kept in one place for the pages that follow it: kit/cmd/review.luau):
--   * a token only the served page knows, from the OS's random source;
--   * the request named this machine by its own name and port (DNS rebinding: an exact match, never a prefix);
--   * a write carries the token in a custom header and comes from this page (Origin / Sec-Fetch-Site);
--   * the page is never shown inside another page's frame (pageHeaders, framed).
-- Nothing here opens a port: a page that listens on anything but 127.0.0.1 is not a local page.
local process = require("@lune/process")

local Run = require("./run")

local LocalPage = {}

-- the page's write token: python's secrets (the OS's CSPRNG); a hash of the clock only when python is missing
function LocalPage.token(): string
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

-- the headers of a page the kit serves on 127.0.0.1. It is never shown inside another site's frame: a framed page's
-- own script still passes every check below (its requests ARE same-origin), so a site that laid it invisibly over
-- its own buttons could make the owner's typing and click an approval of something he cannot see (a review,
-- 2026-11-12). `policy`: the page's own Content-Security-Policy, when it has one.
function LocalPage.pageHeaders(policy: string?): { [string]: string }
	return {
		["Content-Type"] = "text/html; charset=utf-8",
		["Cache-Control"] = "no-store",
		["Content-Security-Policy"] = (if policy then policy .. "; " else "") .. "frame-ancestors 'none'",
		["X-Frame-Options"] = "DENY",
		["Referrer-Policy"] = "no-referrer", -- (a picture's address holds the page's token)
	}
end

-- was the page asked for as a frame of another page? (a browser says what a request is for; a plain client says nothing)
function LocalPage.framed(headers: any): boolean
	local dest = headers["sec-fetch-dest"]
	return dest == "iframe" or dest == "frame" or dest == "embed" or dest == "object" or dest == "fencedframe"
end

-- which bytes of a file a request asks for (its Range header: a browser scrubs a video by asking for a part of it)
-- -> status 200 (no Range, or one this page does not serve - several ranges, another unit, one that is not well
-- formed: a server may answer those with the whole file), 206 with the first and last byte (0-based, both inside the
-- file), or 416 (a range that starts past the file's end)
function LocalPage.range(header: any, total: number): { status: number, first: number, last: number }
	local whole = { status = 200, first = 0, last = total - 1 }
	if type(header) ~= "string" then
		return whole
	end
	local first, last = string.match(header, "^%s*bytes%s*=%s*(%d*)%s*%-%s*(%d*)%s*$")
	if not first or (first == "" and last == "") then
		return whole
	end
	local a: number, b: number
	if first == "" then -- "-N": the last N bytes
		local n = tonumber(last) or 0
		if n <= 0 or total <= 0 then
			return { status = 416, first = 0, last = total - 1 }
		end
		a, b = math.max(0, total - n), total - 1
	else
		a = tonumber(first) or 0
		b = if last == "" then total - 1 else math.min(tonumber(last) or 0, total - 1)
		if last ~= "" and (tonumber(last) or 0) < a then
			return whole -- (a last byte before the first: not a range at all)
		end
		if a >= total then
			return { status = 416, first = 0, last = total - 1 }
		end
	end
	return { status = 206, first = a, last = b }
end

-- did the request name this machine by its own name and this port? (the bare names too: a client that sends no port)
function LocalPage.hostOk(headers: any, port: number): boolean
	local host = string.lower(tostring(headers.host or ""))
	return host == `127.0.0.1:{port}` or host == `localhost:{port}` or host == "127.0.0.1" or host == "localhost"
end

-- may this request write? -> nil, or why not. `header` is the page's own token header (lower case)
function LocalPage.writeProblem(headers: any, port: number, secret: string, header: string): string?
	if headers[header] ~= secret then
		return "missing or wrong page token (reload the page)"
	end
	local origin, site = headers.origin, headers["sec-fetch-site"]
	local mine = origin == nil
		or string.lower(origin) == `http://127.0.0.1:{port}`
		or string.lower(origin) == `http://localhost:{port}`
	if not mine or (site and site ~= "same-origin" and site ~= "none") then
		return "writes come from this page only"
	end
	return nil
end

return LocalPage

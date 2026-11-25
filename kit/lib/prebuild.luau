--!strict
-- prebuild.luau — asked before every build of a piece in vfx / ui / anim / sfx / world (3D: kit/tools/plan.py
-- --prebuild through Content.prebuild). The owner, 2026-11-10, after the car rim's three fixes went to 3D only: "keep
-- going on the 3D ... but don't forget about the other ones" and, on the budgets, "Yes, same budgets" (card b6m2).
--   THE CLOCK (kit/tools/lanecheck.py): 10 minutes a simple piece, 30 a complex one, 60 a hero (the spec's "tier", a
--   screen's "quality"; an effect, a clip, a world and a sound set are complex unless they say; a hero's hour only with
--   the owner's approval); past it no CHANGE to the piece builds - only the owner's words reopen it (`kit clock <lane>
--   <name>`); the piece as it was may still be played, looked at or rebuilt. A change is a change to what the piece is
--   made of (its spec, the assets it names, a dossier's clip sources) - never a look's own output or a note.
--   A LOOK (vfx play / booth) starts no clock for an untouched piece; one that sees the piece CHANGED starts it.
--   THE ROUTE: the switches that change how a piece is made (vfx layer techniques, anim builder + source kinds, ui piece
--   routes + identity, sfx recorded / synth, world terrain / meshes); a route that GAINED a way since its lessons sheet
--   was answered refuses the build until `kit answer <lane> <name> --reroute` and every lesson is answered again.
--   A rerouted sheet (its "## Earlier answers") or one still holding a stub must pass before it builds.
--   A REBUILD OF EVERY PIECE (kit vfx / kit ui / kit sfx all / kit sfx set with no name / kit anim with no name / kit
--   world) holds back a piece past its budget and changed, or made a new way; a piece new or changed since the last
--   such rebuild starts its clock there.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Config = require("./config")
local Locks = require("./locks")
local Run = require("./run")

local Prebuild = {}

-- the lane's folder in the ACTIVE project (--game / games/.active): its piece wins over a kit-home one of the same name
local function activeDir(lane: string): string?
	local key = ({ vfx = "vfx", ui = "ui", world = "worlds", sfx = "sounds", anim = "anims" } :: any)[lane]
	if not key then
		return nil
	end
	local dir = Config.path(key)
	return if lane == "anim" then dir .. "/dossiers" else dir
end

-- the folder holding the file <name>.json in any letter case, from `dirs`
local function findIn(dirs: { string }, name: string): string?
	local want = string.lower(name) .. ".json"
	for _, d in dirs do
		if fs.isDir(d) then
			for _, f in fs.readDir(d) do
				if string.lower(f) == want then
					return d
				end
			end
		end
	end
	return nil
end

-- the piece's own name as its file spells it (pieces are found in any letter case)
function Prebuild.stem(dir: string, name: string): string
	local want = string.lower(name) .. ".json"
	for _, f in if fs.isDir(dir) then fs.readDir(dir) else {} do
		if string.lower(f) == want then
			return string.sub(f, 1, #f - 5)
		end
	end
	return name
end

-- the owner gave the piece a hero's hour (kit approve <lane> <name> "<his words>" --by owner): by any of its names
-- (an anim dossier is approved under a clip it builds), in any letter case
function Prebuild.heroOk(lane: string, ...: string): boolean
	local approvals = Locks.load().approvals
	local mine = if type(approvals) == "table" then approvals[lane] else nil
	if type(mine) ~= "table" then
		return false
	end
	for n, rec in mine do
		if type(n) == "string" and Locks.isOwner(rec) then
			for _, want in { ... } do
				if string.lower(n) == string.lower(want) then
					return true
				end
			end
		end
	end
	return false
end

-- run lanecheck: its lines printed, -> nil to build, or the refusal { summary, next_action }
local function check(argv: { string }, what: string): { summary: string, next_action: string }?
	local res = process.exec(Run.tool("python"), argv)
	local lines = string.split(string.gsub(res.stdout, "\r", ""), "\n")
	local last = #lines
	while last > 0 and not string.match(lines[last], "%S") do
		last -= 1
	end
	local ok, v = pcall(serde.decode, "json" :: any, if last > 0 then lines[last] else "")
	for i = 1, last - 1 do -- (what it says: a clock started, a piece past its budget shown as it was - or why it stops)
		print(lines[i])
	end
	if res.ok and ok and type(v) == "table" and v.status == "pass" then
		return nil
	end
	if ok and type(v) == "table" and v.status == "fail" then
		return { summary = tostring(v.summary), next_action = tostring(v.next_action) }
	end
	local err = string.match(res.stderr, "([^\n]+)%s*$") or "no output"
	return {
		summary = `{what}: the budget and route check crashed ({err})`,
		next_action = `python {table.concat(argv, " ")}`,
	}
end

-- the dossier that builds an anim CLIP (lanecheck reads the dossiers' build blocks): the active project's, then the
-- kit home's -> (its folder, its name) or nil
local function clipDossier(clip: string): (string?, string?)
	local dirs = {}
	local active = activeDir("anim")
	if active and fs.isDir(active) then
		table.insert(dirs, active)
	end
	if active ~= "assets/animations/dossiers" and fs.isDir("assets/animations/dossiers") then
		table.insert(dirs, "assets/animations/dossiers")
	end
	for _, d in dirs do
		local found = process.exec(Run.tool("python"), { "kit/tools/lanecheck.py", "piece", "anim", clip, "--dir", d })
		local okP, vP = pcall(serde.decode, "json" :: any, string.match(found.stdout, "([^\n]+)%s*$") or "")
		if found.ok and okP and type(vP) == "table" and type(vP.piece) == "string" then
			return d, vP.piece
		end
	end
	return nil, nil
end

-- -> nil to build, or the refusal { summary, next_action }. `name`: a piece, an anim CLIP (taken to the dossier that
-- builds it) or a path to a piece's .json (a sound set named by its file). look: playing / capturing the piece as it is
function Prebuild.lane(lane: string, name: string, look: boolean?): { summary: string, next_action: string }?
	local LaneLocks = require("./lanelocks")
	local dir: string?, piece = nil, name
	local asPath = string.gsub(name, "\\", "/")
	if string.sub(asPath, -5) == ".json" and fs.isFile(asPath) then
		dir = string.match(asPath, "^(.*)/[^/]+$") or "."
		piece = string.match(asPath, "([^/]+)%.json$") or name
	else
		local active = activeDir(lane)
		dir = (if active then findIn({ active }, name) else nil) or LaneLocks.pieceDir(lane, name)
	end
	if lane == "anim" and not dir then
		dir, piece = clipDossier(name)
		piece = piece or name
	end
	if not dir then
		return nil -- (no such piece, or a clip no dossier builds: the lane's own command says what it needs)
	end
	piece = Prebuild.stem(dir, piece)
	local argv = { "kit/tools/lanecheck.py", "prebuild", lane, piece, "--dir", dir }
	if Prebuild.heroOk(lane, piece, name) then
		table.insert(argv, "--hero-ok")
	end
	if look then
		table.insert(argv, "--look")
	end
	local stop = check(argv, `{lane} {piece}`)
	if stop then
		return stop
	end
	-- a rerouted sheet (its Earlier answers) or one still holding a stub owes its answers before a build: the lanes'
	-- quality locks read the sheets in kit verify, never at every build
	local path = LaneLocks.sheetPath(dir, piece)
	if fs.isFile(path) then
		local text = fs.readFile(path)
		if string.find(text, "\n## Earlier answers", 1, true) or string.find(text, "<answer>", 1, true) then
			local r = require("./answers").check(text, lane, path)
			if #r.problems > 0 then
				return {
					summary = `{lane} {piece}: STOP — its lessons are not answered yet: {r.problems[1]}`,
					next_action = `answer them in {path}, then: lune run kit answer {lane} {piece}`,
				}
			end
		end
	end
	return nil
end

-- a rebuild of every piece of the lane in the folder `laneDir` (its project's): -> nil to build, or the refusal
function Prebuild.all(lane: string, laneDir: string): { summary: string, next_action: string }?
	local argv = { "kit/tools/lanecheck.py", "prebuild-all", lane, "--dir", laneDir }
	local approvals = Locks.load().approvals
	local mine = if type(approvals) == "table" then approvals[lane] else nil
	local heroes = {}
	if type(mine) == "table" then
		for n, rec in mine do
			if type(n) == "string" and Locks.isOwner(rec) then
				table.insert(heroes, n)
			end
		end
	end
	if #heroes > 0 then
		table.insert(argv, "--approved")
		table.insert(argv, table.concat(heroes, ","))
	end
	return check(argv, `{lane} (every piece)`)
end

-- the refusal as a kit report (its exit code), or nil to build
function Prebuild.held(lane: string, name: string?, look: boolean?): number?
	if not name or name == "" or string.sub(name, 1, 2) == "--" then
		return nil
	end
	local stop = Prebuild.lane(lane, name, look)
	if stop then
		return Run.report(lane, {}, Run.CODES.CONTENT, stop.summary, stop.next_action)
	end
	return nil
end

-- a rebuild of every piece: the refusal as a kit report, or nil to build
function Prebuild.heldAll(lane: string, laneDir: string): number?
	local stop = Prebuild.all(lane, laneDir)
	if stop then
		return Run.report(lane, {}, Run.CODES.CONTENT, stop.summary, stop.next_action)
	end
	return nil
end

return Prebuild

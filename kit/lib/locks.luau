-- locks.luau — the shared rules behind every lane's quality lock (board/locks.json): a piece made before the locks is
-- grandfathered, a new piece needs the OWNER's approval (`kit approve`) or waiver for a step, and a file in the
-- project's own build output is a render of our work, never a real source.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Locks = {}

Locks.FILE = "board/locks.json" -- per project (board/ is the project's own record; kit/ is copied into every project)
-- true once a command pointed FILE at a FIXTURE project's own record (kit review --models --locks): only then may an
-- approval name another models folder - a fixture's sheet id written into the project's record would read "changed"
Locks.fixture = false

local cached: any = nil

local function empty(): any
	return { grandfathered = {}, approvals = {}, waivers = {} }
end

-- the decoded locks file, or the empty shape when it is missing / invalid; cached until reset()
function Locks.load(): any
	if cached then
		return cached
	end
	if not fs.isFile(Locks.FILE) then
		cached = empty()
		return cached
	end
	local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(Locks.FILE))
	cached = if ok and type(data) == "table" then data else empty()
	return cached
end

function Locks.reset()
	cached = nil
end

-- write the locks file back (kit approve)
function Locks.save(data: any)
	fs.writeFile(Locks.FILE, serde.encode("json", data, true) .. "\n")
	cached = data
end

local function trimmed(text: string): string
	return string.match(text, "^%s*(.-)%s*$") or text
end

-- an approval record counts only when it is the OWNER's: a model may propose, never approve its own work
function Locks.isOwner(rec: any): boolean
	if type(rec) ~= "table" then
		return false
	end
	if rec.who ~= nil and (type(rec.who) ~= "string" or string.lower(rec.who) ~= "owner") then
		return false
	end
	local by = if rec.by ~= nil then rec.by else rec.who
	if type(by) ~= "string" then
		return false
	end
	return string.sub(string.lower(trimmed(by)), 1, 5) == "owner"
end

-- a path in the project's own build output: a frame or reference that lives there is a render of our work. Any
-- `build` folder counts (case-insensitive, `..` resolved, a sandbox worktree's or a game's build/ too) and the
-- configured build folder.
function Locks.isBuildPath(path: string): boolean
	local low = string.lower(Locks.normal(path))
	if string.sub(low, 1, 6) == "build/" or string.find(low, "/build/", 1, true) then
		return true
	end
	local ok, configured = pcall(function()
		return string.lower(Locks.normal(require("./config").path("build")))
	end)
	if ok and type(configured) == "string" and configured ~= "" then
		local prefix = if string.sub(configured, -1) == "/" then configured else configured .. "/"
		return string.sub(low, 1, #prefix) == prefix
	end
	return false
end

-- `.` and `..` segments resolved (a leading `..` that leaves the project is kept)
local function resolve(path: string): string
	local absolute = string.sub(path, 1, 1) == "/"
	local out = {}
	for seg in string.gmatch(path, "[^/]+") do
		if seg == ".." and #out > 0 and out[#out] ~= ".." then
			table.remove(out)
		elseif seg ~= "." then
			table.insert(out, seg)
		end
	end
	return (if absolute then "/" else "") .. table.concat(out, "/")
end

-- project-relative form: `/` separators, `.` / `..` resolved, and an absolute path inside the project made relative
function Locks.normal(path: string): string
	local normal = resolve((string.gsub(path, "\\", "/")))
	local root = resolve((string.gsub(process.cwd, "\\", "/")))
	if string.sub(root, -1) ~= "/" then
		root ..= "/"
	end
	if string.lower(string.sub(normal, 1, #root)) == string.lower(root) then
		normal = string.sub(normal, #root + 1)
	end
	return normal
end

-- point this process at a FIXTURE project's own record (kit review / kit approve --locks <file>, with --models or
-- --effects): returns why not, or nil when done. A fixture's record lives under THIS project's build/ folder
-- (git-ignored), plainly spelled. That rule needs no list of the spellings one file can have (./board/locks.json,
-- BOARD\locks.json, the absolute path, and on Windows "locks.json." with a trailing dot, an 8.3 short name, a
-- ::$DATA stream): whatever is not plainly under build/ is refused, and so is a path there whose real place (through
-- a junction or a link) is some project's board/locks.json - so a fixture folder's piece is never written into a
-- project's own record, where its id would read as that piece "changed".
function Locks.useFixture(path: string): string?
	local normal = Locks.normal(path)
	local plain = string.sub(normal, 1, 6) == "build/" and string.find(normal, '[:~%*%?"<>|]') == nil
	for seg in string.gmatch(normal, "[^/]+") do
		-- (Windows reads "x." and "x " as "x"; a ".." still here would leave build/)
		if seg == ".." or string.find(seg, "[%. ]$") then
			plain = false
		end
	end
	local refused =
		"--locks is not a fixture's own record: that is a plainly spelled file under this project's build/ folder (git-ignored), never the project's board/locks.json under any spelling"
	if not plain then
		return refused
	end
	-- ... and its REAL place is no project's record either: a folder under build/ can be a junction or a link (the
	-- prove sandbox's build/selftest is one, into the project it proves - which is why "under build/" is asked of
	-- the spelling, and this of where it leads)
	local ok, res = pcall(process.exec, require("./run").tool("python"), {
		"-c",
		"import os,sys; print(os.path.normcase(os.path.realpath(sys.argv[1])).replace(os.sep, '/'))",
		normal,
	})
	local real = if ok and res.ok then (string.gsub(res.stdout, "%s+$", "")) else ""
	if real == "" or string.sub(real, -17) == "/board/locks.json" then
		return refused
	end
	Locks.FILE = normal
	Locks.fixture = true
	Locks.reset()
	return nil
end

-- true when the piece existed before the locks: its normalized path is in the lane's list
function Locks.grandfathered(lane: string, path: string): boolean
	local lists = Locks.load().grandfathered
	if type(lists) ~= "table" then
		return false
	end
	local files = lists[lane]
	if type(files) ~= "table" then
		return false
	end
	-- case-insensitive: Windows file names are (kit asset Glock finds build_glock.py)
	local normal = string.lower(Locks.normal(path))
	for _, file in files do
		if type(file) == "string" and string.lower(file) == normal then
			return true
		end
	end
	return false
end

local function ownerRecord(key: string, lane: string, name: string): any?
	local records = Locks.load()[key]
	if type(records) ~= "table" then
		return nil
	end
	local byLane = records[lane]
	if type(byLane) ~= "table" then
		return nil
	end
	local rec = byLane[name]
	if Locks.isOwner(rec) then
		return rec
	end
	return nil
end

-- the 3D reference-study lock came after the others (2026-10-28): the build scripts that exist the first time it runs
-- are its grandfathered list (`grandfathered["3d-study"]`), frozen once into the project's locks file, so a piece
-- already under way is never stopped half-built; every piece started after it needs its study (kit study).
Locks.STUDY_LANE = "3d-study"
local STUDY_GLOBS = { "assets/models", "games/*/assets/models" }

local function studyScripts(): { string }
	local out = {}
	local function scan(dir: string)
		if fs.isDir(dir) then
			for _, f in fs.readDir(dir) do
				if string.match(f, "%.py$") then
					table.insert(out, `{dir}/{f}`)
				end
			end
		end
	end
	for _, pattern in STUDY_GLOBS do
		if string.find(pattern, "*", 1, true) then
			if fs.isDir("games") then
				for _, game in fs.readDir("games") do
					scan(`games/{game}/assets/models`)
				end
			end
		else
			scan(pattern)
		end
	end
	table.sort(out)
	return out
end

-- freeze one lane's grandfathered list (`lane`, its date under `stamp`) in Locks.FILE when it has none yet -> true when
-- this call froze it: every build script that exists right now is on it, so a piece made after is held. The study,
-- stage and methods locks share it.
local function freezeList(lane: string, stamp: string): boolean
	if not fs.isFile(Locks.FILE) then
		return false
	end
	local g = Locks.load().grandfathered
	if type(g) == "table" and g[lane] ~= nil then
		return false
	end
	Locks.reset() -- (re-read right before the write: another session may have approved something since)
	local data = Locks.load()
	if type(data.grandfathered) ~= "table" then
		data.grandfathered = {}
	end
	if data.grandfathered[lane] ~= nil then
		return false
	end
	data.grandfathered[lane] = studyScripts()
	data[stamp] = os.date("!%Y-%m-%d")
	Locks.save(data)
	return true
end

-- freeze the study lock's list when it has none yet -> true when this call froze it
function Locks.freezeStudy(): boolean
	return freezeList(Locks.STUDY_LANE, "study_lock")
end

-- true when this build script predates the study lock; the first call in a project with a locks file freezes the list
function Locks.studyExempt(script: string): boolean
	if Locks.FILE == "board/locks.json" then
		Locks.freezeStudy()
	end
	return Locks.grandfathered(Locks.STUDY_LANE, script)
end

-- the 3D STAGE approvals came after the others (2026-11-11, the owner: "A concept sheet we really need ... block[out]
-- approval"): a complex / hero / aaa piece builds only from a model sheet he approved, and bakes only after he approved
-- its blockout. The build scripts that exist the first time this runs are its grandfathered list
-- (`grandfathered["3d-stages"]`), frozen once like the study lock's, so a piece already under way is never stopped.
Locks.STAGES_LANE = "3d-stages"

-- freeze the stage approvals' list when it has none yet -> true when this call froze it
function Locks.freezeStages(): boolean
	return freezeList(Locks.STAGES_LANE, "stages_lock")
end

-- true when this build script predates the stage approvals; the first call in a project with a locks file freezes the list
function Locks.stagesExempt(script: string): boolean
	if Locks.FILE == "board/locks.json" then
		Locks.freezeStages()
	end
	return Locks.grandfathered(Locks.STAGES_LANE, script)
end

-- the METHODS lock came last (2026-11-13, the owner: "every method i mentioned ... implmented into each pipeline and
-- enforced in the terms of being used"): a new piece's parts plan names the builder call each coded part is made
-- with, and its build is held to that plan (kit/blender/rbx_plan.py methods_locked / method_problems /
-- methods_check). The build scripts that exist the first time this runs are its grandfathered list
-- (`grandfathered["3d-methods"]`), frozen once, so no piece already made is stopped.
Locks.METHODS_LANE = "3d-methods"

-- freeze the methods lock's list in Locks.FILE when it has none yet -> true when this call froze it. (A project
-- with no piece yet freezes an EMPTY list, which Lune writes as {}: rbx_plan.methods_locked reads that as a list.)
function Locks.freezeMethods(): boolean
	return freezeList(Locks.METHODS_LANE, "methods_lock")
end

-- freeze the study, stage and methods lists that are not frozen yet (2026-11-18, card 988z: kit new asset froze
-- only the methods list before writing a piece's script, so in a new project the first kit plan froze that piece
-- onto the study and stage lists as old - exempt from both). Called by kit new asset BEFORE its script exists and by
-- every build's pre-build step.
function Locks.freezeAll()
	if Locks.FILE == "board/locks.json" then
		Locks.freezeStudy()
		Locks.freezeStages()
		Locks.freezeMethods()
	end
end

-- true when this build script predates the methods lock; the first call in a project with a locks file freezes
-- the list. Called wherever a piece starts or is built (kit new asset BEFORE its script is written, kit plan, kit
-- asset's pre-build step): a piece made after the first of those is never on the list.
function Locks.methodsExempt(script: string): boolean
	if Locks.FILE == "board/locks.json" then
		Locks.freezeMethods()
	end
	return Locks.grandfathered(Locks.METHODS_LANE, script)
end

-- the owner's approval of ONE stage's artefact of a piece (`kit approve <lane> <name> "<words>" --by owner --stage
-- <step>`: a model sheet, a blockout), or nil. The record names the artefact's id he saw (`id`): the caller compares
-- it with the artefact as it is now - a sheet that changed needs his word again.
function Locks.stage(lane: string, name: string, step: string): any?
	local stages = Locks.load().stages
	if type(stages) ~= "table" or type(stages[lane]) ~= "table" or type(stages[lane][name]) ~= "table" then
		return nil
	end
	local rec = stages[lane][name][step]
	return if Locks.isOwner(rec) then rec else nil
end

-- the owner's go-ahead for one piece (its chart, references or brief, written by `kit approve`), or nil
function Locks.approval(lane: string, name: string): any?
	return ownerRecord("approvals", lane, name)
end

-- the owner's waiver for one piece (a step it may skip, e.g. synth-only sound), or nil; `step` names the step when
-- the waiver lists them (`steps`), a waiver without a list covers every step
function Locks.waiver(lane: string, name: string, step: string?): any?
	local rec = ownerRecord("waivers", lane, name)
	if rec and step and type(rec.steps) == "table" and not table.find(rec.steps, step) then
		return nil
	end
	return rec
end

return Locks

-- accept.luau — the accept RATCHET for every kind (mission 06 5.8): `kit accept <kind> <name>` locks the measured state
-- of a build the OWNER rated >= 7 as its floor; `kit verify` fails when a later build measures worse past tolerance.
-- (3D assets keep their own floor in kit/cmd/judge.luau: `kit accept <asset>` / `kit accept asset <asset>`.)
--
-- Per kind, the floor holds NUMBERS (gated: a worse value past the tolerance fails) and HASHES (the source and the
-- evidence the owner judged: a change is reported, never failed — the owner's eye re-judges it):
--   vfx <effect>    booth checks failed (lower is better); the effect json + its preview sheet
--   screen <Name>   the screen json + its preview sheet (the gates: kit ui inside verify)
--   sound <name>    the recipe + its render; the owner's ears ARE the measure (a newer owner verdict below the floor fails)
--   world <Name>    kit world check errors / warnings (lower is better); the blueprint
--   anim <Name>     the clip's measured problems (lower is better); the clip json + its strip
--   system <Game>   spec cases + regression cases (higher is better; dropping one fails); the shared modules
-- A floor is written only when the vault holds an OWNER verdict >= 7 on that piece (kit verdict is the owner's record).
-- Lowering a floor or moving it is the owner's act at their own terminal (Owner.confirm), never a model's.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Vault = require("../lib/vault")

local Accept = {}

Accept.KINDS = { "vfx", "screen", "sound", "world", "anim", "system" }
Accept.DIR = "assets/floors"
-- per number: which way is better and how far worse a later build may measure before verify fails
Accept.RULES = {
	booth_failed = { better = "lower", tolerance = 0 },
	check_errors = { better = "lower", tolerance = 0 },
	check_warnings = { better = "lower", tolerance = 2 },
	problems = { better = "lower", tolerance = 0 },
	spec_cases = { better = "higher", tolerance = 0 },
	regression_cases = { better = "higher", tolerance = 0 },
	owner_score = { better = "higher", tolerance = 1 },
}

local function readJson(path: string): any
	if not fs.isFile(path) then
		return nil
	end
	local ok, v = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return if ok then v else nil
end

local function sha(paths: { string }): string?
	local parts, any = {}, false
	for _, p in paths do
		if fs.isFile(p) then
			table.insert(parts, p .. "\0" .. fs.readFile(p))
			any = true
		end
	end
	return if any then serde.hash("sha256", table.concat(parts, "\0")) else nil
end

local function first(paths: { string }): string?
	for _, p in paths do
		if fs.isFile(p) then
			return p
		end
	end
	return nil
end

local function countCases(dir: string): number
	local n = 0
	if not fs.isDir(dir) then
		return 0
	end
	for _, f in fs.readDir(dir) do
		if string.sub(f, -10) == ".spec.luau" then
			for _ in string.gmatch(fs.readFile(dir .. "/" .. f), "test%.case%(") do
				n += 1
			end
		end
	end
	return n
end

-- the owner's newest verdict on a piece (vault notes by the owner, not inferred): (score, note) or nil
function Accept.ownerVerdict(kind: string, name: string): (number?, any)
	local dept = Vault.dept(kind)
	if not dept then
		return nil, nil
	end
	for _, n in Vault.verdicts(dept) do
		local f = n.front
		if string.lower(tostring(f.name)) == string.lower(name) and f.source == "owner" and f.inferred ~= true then
			local s = tonumber(f.score)
			if s then
				return s, n
			end
		end
	end
	return nil, nil
end

-- the lookup accept / measure use (a spec swaps in a stand-in vault)
Accept.verdictOf = Accept.ownerVerdict

export type Measure = { numbers: { [string]: number }, hashes: { [string]: string }, missing: string? }

-- the measured state of one piece, from files only (no render, no Studio); `root` = "" or "games/<Name>/"
function Accept.measure(kind: string, name: string, root: string, worldCheck: ((string) -> any)?): Measure
	local nums, hashes = {}, {}
	local function hash(key: string, paths: { string })
		local h = sha(paths)
		if h then
			hashes[key] = h
		end
	end
	if kind == "vfx" then
		local src = root .. "assets/effects/" .. name .. ".json"
		if not fs.isFile(src) then
			return { numbers = nums, hashes = hashes, missing = src }
		end
		hash("source", { src })
		hash("evidence", { root .. "build/vfx/" .. name .. ".png" })
		local m = readJson(first({
			root .. "build/vfx/booth/" .. name .. "_play.metrics.json",
			root .. "build/vfx/booth/" .. name .. ".metrics.json",
		}) or "")
		if type(m) == "table" and type(m.views) == "table" then
			local failed = 0
			for _, v in m.views do
				for _, c in (if type(v) == "table" and type(v.checks) == "table" then v.checks else {}) do
					if type(c) == "table" and c.ok == false then
						failed += 1
					end
				end
			end
			nums.booth_failed = failed
		end
	elseif kind == "screen" then
		local src = root .. "assets/ui/" .. name .. ".json"
		if not fs.isFile(src) then
			return { numbers = nums, hashes = hashes, missing = src }
		end
		hash("source", { src })
		hash("evidence", { root .. "build/ui/" .. name .. ".png" })
	elseif kind == "sound" then
		local src = root .. "assets/sounds/" .. name .. ".json"
		if not fs.isFile(src) then
			return { numbers = nums, hashes = hashes, missing = src }
		end
		hash("source", { src })
		hash("evidence", { root .. "build/sounds/" .. name .. ".ogg" })
		local s = Accept.verdictOf("sound", name)
		if s then
			nums.owner_score = s
		end
	elseif kind == "world" then
		local src = root .. "assets/worlds/" .. name .. ".json"
		if not fs.isFile(src) then
			return { numbers = nums, hashes = hashes, missing = src }
		end
		hash("source", { src })
		local compiled = root .. "build/worlds/" .. name .. ".json"
		if worldCheck and fs.isFile(compiled) then
			local r = worldCheck(compiled)
			local summary = if type(r) == "table" then tostring(r.summary or "") else ""
			local e, w = string.match(summary, "(%d+) error%(s%)"), string.match(summary, "(%d+) warning%(s%)")
			if e then
				nums.check_errors = tonumber(e) :: number
			end
			if w then
				nums.check_warnings = tonumber(w) :: number
			end
		end
	elseif kind == "anim" then
		local src = first({
			root .. "assets/animations/" .. name .. ".json",
			root .. "assets/animations/" .. name .. ".pose.json",
		})
		if not src then
			return { numbers = nums, hashes = hashes, missing = root .. "assets/animations/" .. name .. ".json" }
		end
		hash("source", { src })
		hash("evidence", { root .. "build/animations/" .. name .. ".png" })
		local m = readJson(root .. "build/animations/" .. name .. ".metrics.json")
		if type(m) == "table" and type(m.problems) == "table" then
			nums.problems = #m.problems
		end
	elseif kind == "system" then
		local game = root ~= "" and fs.isDir(root)
		if not game then
			return { numbers = nums, hashes = hashes, missing = "games/" .. name .. "/" }
		end
		nums.spec_cases = countCases(root .. "tests")
		local corpus = readJson(root .. "tests/regressions.json")
		nums.regression_cases = if type(corpus) == "table" and type(corpus.cases) == "table" then #corpus.cases else 0
		local shared = {}
		if fs.isDir(root .. "src/shared") then
			for _, f in fs.readDir(root .. "src/shared") do
				table.insert(shared, root .. "src/shared/" .. f)
			end
			table.sort(shared)
		end
		hash("source", shared)
	else
		return { numbers = nums, hashes = hashes, missing = `a kind (one of {table.concat(Accept.KINDS, ", ")})` }
	end
	return { numbers = nums, hashes = hashes }
end

-- floor vs now -> (failures, notes): a number worse than its floor past the tolerance fails; a changed hash is a note
function Accept.compare(floor: any, now: Measure): ({ string }, { string })
	local fails, notes = {}, {}
	for key, was in (if type(floor.numbers) == "table" then floor.numbers else {}) do
		local rule = Accept.RULES[key] or { better = "lower", tolerance = 0 }
		local is = now.numbers[key]
		if is == nil then
			table.insert(notes, `{key}: not measured now (floor {was})`)
		else
			local worse = if rule.better == "lower" then is - was else was - is
			if worse > rule.tolerance then
				table.insert(fails, `{key} {was} -> {is} ({rule.better} is better; tolerance {rule.tolerance})`)
			end
		end
	end
	for key, was in (if type(floor.hashes) == "table" then floor.hashes else {}) do
		if now.hashes[key] ~= nil and now.hashes[key] ~= was then
			table.insert(notes, `{key} changed since the owner's {floor.verdict and floor.verdict.score or "?"}/10`)
		end
	end
	return fails, notes
end

function Accept.floorPath(root: string, kind: string, name: string): string
	return `{root}{Accept.DIR}/{kind}/{name}.accepted.json`
end

-- every floor in the project and in every game: { {root, kind, name, path, floor} }
function Accept.floors(): { any }
	local out = {}
	local roots = { "" }
	if fs.isDir("games") then
		for _, g in fs.readDir("games") do
			if string.sub(g, 1, 1) ~= "." and fs.isDir("games/" .. g) then
				table.insert(roots, "games/" .. g .. "/")
			end
		end
		table.sort(roots)
	end
	for _, root in roots do
		local base = root .. Accept.DIR
		if fs.isDir(base) then
			for _, kind in Accept.KINDS do
				if fs.isDir(base .. "/" .. kind) then
					for _, f in fs.readDir(base .. "/" .. kind) do
						local name = string.match(f, "^(.+)%.accepted%.json$")
						if name then
							local path = `{base}/{kind}/{f}`
							table.insert(
								out,
								{ root = root, kind = kind, name = name, path = path, floor = readJson(path) }
							)
						end
					end
				end
			end
		end
	end
	return out
end

-- accept: (ok, summary, next_action, path?) — the vault must hold the owner's >= 7; a floor already there moves only
-- up (a worse measure, or a lower verdict, is the owner's act: `confirm` is Owner.confirm)
function Accept.accept(
	kind: string,
	name: string,
	root: string,
	words: string,
	lower: boolean,
	worldCheck: ((string) -> any)?,
	confirm: ((string, string) -> (boolean, string?))?
): (boolean, string, string, string?)
	if not table.find(Accept.KINDS, kind) then
		return false,
			`accept: unknown kind "{kind}"`,
			`lune run kit accept <{table.concat(Accept.KINDS, "|")}> <name>   (3D: lune run kit accept <asset>)`
	end
	local score, note = Accept.verdictOf(kind, name)
	if not score or score < 7 then
		return false,
			`accept: {kind} {name} has no OWNER verdict >= 7 in the vault{if score
				then " (newest: " .. score .. "/10)"
				else ""} — a floor is a build the owner rated >= 7`,
			`the owner judges it: lune run kit verdict {kind} {name} <0-10> "<the owner's words>"`
	end
	local now = Accept.measure(kind, name, root, worldCheck)
	if now.missing then
		return false, `accept: {kind} {name}: missing {now.missing}`, "build it first, then accept it"
	end
	local path = Accept.floorPath(root, kind, name)
	local old = readJson(path)
	if type(old) == "table" then
		local fails = Accept.compare(old, now)
		local oldScore = if type(old.verdict) == "table" then tonumber(old.verdict.score) else nil
		if oldScore and score < oldScore then
			table.insert(fails, `the owner's score {oldScore} -> {score}`)
		end
		if #fails > 0 then
			if not lower then
				return false,
					`accept: {kind} {name} measures below its floor ({fails[1]}) — a floor is lowered only by the owner`,
					`only if the OWNER approved THIS build: lune run kit accept {kind} {name} "<their words>" --lower  (they confirm it at their terminal)`
			end
			local ok, why = (confirm :: any)(`OWNER: lower {kind} {name}'s floor ({fails[1]})`, name)
			if not ok then
				return false,
					`accept: {why}`,
					`the owner runs  lune run kit accept {kind} {name} "<their words>" --lower  in their own terminal`
			end
		end
	end
	local dir = `{root}{Accept.DIR}/{kind}`
	local cur = ""
	for _, part in string.split(dir, "/") do
		cur = if cur == "" then part else cur .. "/" .. part
		if cur ~= "" and not fs.isDir(cur) then
			fs.writeDir(cur)
		end
	end
	fs.writeFile(path, serde.encode("json", {
		kind = kind,
		name = name,
		numbers = now.numbers,
		hashes = now.hashes,
		verdict = { score = score, date = note and note.front.date, note = note and note.rel },
		note = if words ~= "" then words else nil,
		lowered = if type(old) == "table" and lower then true else nil,
		at = os.date("!%Y-%m-%dT%H:%M:%SZ"),
	}, true) .. "\n")
	local shown = {}
	for k, v in now.numbers do
		table.insert(shown, `{k} {v}`)
	end
	table.sort(shown)
	return true,
		`accept: {kind} {name} (the owner's {score}/10) is the floor now{if #shown > 0
			then " — " .. table.concat(shown, ", ")
			else " — its source + evidence hashes (the owner's eye re-judges a change)"}`,
		`commit {path}; kit verify fails when a later build measures worse`,
		path
end

-- every floor re-measured: (ok, lines, summary)
function Accept.checkAll(worldCheck: ((string) -> any)?): (boolean, { string }, string)
	local lines, failed, n = {}, 0, 0
	for _, f in Accept.floors() do
		n += 1
		if type(f.floor) ~= "table" then
			failed += 1
			table.insert(lines, `{f.path}: unreadable floor`)
			continue
		end
		local now = Accept.measure(f.kind, f.name, f.root, worldCheck)
		if now.missing then
			failed += 1
			table.insert(lines, `{f.kind} {f.name}: missing {now.missing} (a floor's piece was deleted)`)
			continue
		end
		-- (a sound's owner_score is its newest owner verdict: one the owner gave below the floor fails here)
		local fails, notes = Accept.compare(f.floor, now)
		if #fails > 0 then
			failed += 1
			table.insert(lines, `{f.kind} {f.name}: BELOW ITS FLOOR — {table.concat(fails, "; ")}`)
		end
		for _, x in notes do
			table.insert(lines, `{f.kind} {f.name}: {x}`)
		end
	end
	local summary = if n == 0
		then "no accepted floors yet (kit accept <kind> <name> after the owner rates a build >= 7)"
		elseif failed == 0 then `{n} floor(s) held`
		else `{failed} of {n} floor(s) broken`
	return failed == 0, lines, summary
end

-- the python world check as a function (verify + accept): the decoded verdict line, or nil
function Accept.worldCheck(python: string): (string) -> any
	return function(compiled: string): any
		local out = string.gsub(compiled, "[^/]+%.json$", "checks")
		local r = process.exec(python, { "kit/world/worldcheck.py", compiled, "--out", out })
		local last = nil
		for line in string.gmatch(r.stdout or "", "[^\n]+") do
			last = line
		end
		local ok, v = pcall(serde.decode, "json" :: any, last or "")
		return if ok then v else nil
	end
end

return Accept

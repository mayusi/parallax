-- learn.luau — the kit gets better every time it is used, in every project.
--   kit lesson <area> "..."     record something non-obvious you learned (a gotcha, a technique that worked)
--   kit lessons [area]          read them — `kit new` shows the relevant ones automatically
--   kit grades [--write]        how well the quality score follows the owner's grades; refit its weights to them
--   kit promote <kind> <name>   add a proven piece of content (its gate passed after its last edit) to the
--                               example library, so any project can `kit new <kind> x --from <name>`
--   kit sync                    pull the latest kit + lessons + examples from the kit's home into this project
-- Where it goes: the kit's HOME copy (the folder `kit install` copied from, recorded in kit/HOME), so every
-- project receives it on its next `kit update` / `kit sync`. The project also keeps its own record
-- (board/lessons/). In the kit's home itself, kit/lessons and kit/starter are written directly.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Board = require("../lib/board")
local Config = require("../lib/config")
local Library = require("../lib/library")
local Origin = require("../lib/origin")
local Owner = require("../lib/owner")
local Routes = require("../lib/routes")
local Run = require("../lib/run")
local Vault = require("../lib/vault")

local C = Run.CODES
local Learn = {}

Learn.AREAS = {
	["3d"] = "3D models (Blender pipeline)",
	vfx = "effects",
	sfx = "sounds",
	ui = "screens / GUI",
	world = "levels / maps",
	anim = "animations",
	code = "gameplay code, networking, data",
	qa = "testing, playtests, performance",
	kit = "the kit itself, harnesses, workflow",
}
-- `kit new <kind>` -> the area whose lessons to show
Learn.AREA_OF = {
	asset = "3d",
	vfx = "vfx",
	sound = "sfx",
	screen = "ui",
	world = "world",
	anim = "anim",
	system = "code",
	playtest = "qa",
}

-- the kit's home folder ("" = this project IS the home, or its kit/HOME points nowhere: Learn.homeProblem)
function Learn.home(): string
	return Origin.home()
end

-- kit/HOME exists but points nowhere (the home moved): a problem to report, never a silent "this is the home"
function Learn.homeProblem(): string?
	if fs.isFile("kit/HOME") and Learn.home() == "" then
		local h = string.gsub(fs.readFile("kit/HOME"), "%s+$", "")
		return `kit/HOME points to "{h}", which has no kit/ — fix that path (or re-run kit install from the home)`
	end
	return nil
end

local function prefix(root: string): string
	return if root == "" then "" else root .. "/"
end

local function lessonFile(root: string, area: string): string
	return `{prefix(root)}kit/lessons/{area}.md`
end

local function readLines(path: string): { string }
	local out = {}
	if fs.isFile(path) then
		for line in string.gmatch(fs.readFile(path), "[^\n]+") do
			if string.sub(line, 1, 2) == "- " then
				table.insert(out, line)
			end
		end
	end
	return out
end

-- every lesson for an area: shipped with the kit + this project's own (deduplicated, oldest first)
function Learn.lessons(area: string): { string }
	local seen, out = {}, {}
	local function add(line: string)
		local key = string.match(line, "%):%s*(.*)$") or line
		if not seen[key] then
			seen[key] = true
			table.insert(out, line)
		end
	end
	-- a lesson the vault marks superseded (Vault.supersede) is retired from every view, the flat files included
	local dept0 = Vault.dept(area)
	local retired = if dept0 and Vault.exists() then Vault.retiredLessonTexts(dept0) else {}
	for _, path in { lessonFile("", area), Board.dir(`lessons/{area}.md`) } do
		for _, line in readLines(path) do
			local text = string.match(line, "%):%s*(.*)$") or line
			text = string.gsub(string.gsub(string.gsub(text, "%s+", " "), "^%s+", ""), "%s+$", "")
			if not retired[text] then
				add(line)
			end
		end
	end
	-- the vault (kit/knowledge/vault/<area>/lessons: one note each) is the record; the files above are its views
	local dept = Vault.dept(area)
	if dept and Vault.exists() then
		for _, line in Vault.lessons(dept) do
			add(line)
		end
	end
	return out
end

local function append(path: string, header: string, line: string)
	local parent = string.match(path, "^(.*)/[^/]+$")
	if parent then
		Config.ensureDir(parent)
	end
	local text = if fs.isFile(path) then fs.readFile(path) else `# Lessons — {header}\n\n`
	if string.sub(text, -1) ~= "\n" then
		text ..= "\n"
	end
	fs.writeFile(path, text .. line .. "\n")
end

local function projectName(): string
	local ok, cfg = pcall(Config.load)
	return if ok and cfg and cfg.name then tostring(cfg.name) else "project"
end

-- the kit's measuring-code version (rbx_score.MEASURE_VERSION): grades and floors carry the one they were measured by
local function measureVersion(): number?
	local ok, src = pcall(fs.readFile, "kit/blender/rbx_score.py")
	local v = if ok then string.match(src, "\nMEASURE_VERSION = (%d+)") else nil
	return if v then tonumber(v) else nil
end

-- the CANONICAL grades / weights: the kit home's copy (every project's grades) — or this repo's own when it is the
-- home. They are changed there, in place, and only ever copied DOWN to a project (a project's copy is a snapshot)
local function canonical(file: string): string
	local home = Learn.home()
	return if home == "" then `kit/{file}` else `{prefix(home)}kit/{file}`
end

local function syncFromHome(file: string)
	if Learn.home() ~= "" and fs.isFile(canonical(file)) then
		fs.writeFile(`kit/{file}`, fs.readFile(canonical(file)))
	end
end

-- every file of a home folder (kit/anchors) copied down into this project's
local function syncDirFromHome(dir: string)
	local from = canonical(dir)
	if Learn.home() ~= "" and fs.isDir(from) then
		Config.ensureDir(`kit/{dir}`)
		for _, f in fs.readDir(from) do
			if fs.isFile(`{from}/{f}`) then
				fs.writeFile(`kit/{dir}/{f}`, fs.readFile(`{from}/{f}`))
			end
		end
	end
end

-- a build script's identity: sha256 of its text with LF line endings (git may check it out with CRLF) — a grade
-- remembers the script the owner judged, so a re-measure can never pin an old grade on an edited model
local function scriptSha(path: string): string?
	local ok, text = pcall(fs.readFile, path)
	if not ok then
		return nil
	end
	return string.sub(serde.hash("sha256", (string.gsub(text, "\r\n", "\n"))), 1, 16)
end

-- a BUILD's identity (rbx_score.build_identity, kept in step): its script's text with LF endings — and the a.param values
-- kept beside it (build_<x>.py -> <x>.params.json), when there are any: the same script with other numbers is another
-- model. Without kept values it is the script's own sha.
local function buildSha(path: string): string?
	local ok, text = pcall(fs.readFile, path)
	if not ok then
		return nil
	end
	text = (string.gsub(text, "\r\n", "\n"))
	local dir, file = string.match(path, "^(.*)[/\\]([^/\\]+)$")
	local stem = (string.gsub(file or path, "%.py$", ""))
	if string.sub(stem, 1, 6) == "build_" then
		stem = string.sub(stem, 7)
	end
	local params = `{dir or "."}/{stem}.params.json`
	if fs.isFile(params) then
		text ..= "\n#a.param\n" .. (string.gsub(fs.readFile(params), "\r\n", "\n"))
	end
	-- the pack's chosen values a build reads (kit pack: <x>.pack.json "inputs_sha" — rbx_score.pack_inputs)
	local pack = `{dir or "."}/{stem}.pack.json`
	if fs.isFile(pack) then
		local okPack, data = pcall(serde.decode, "json", fs.readFile(pack))
		local sha = if okPack and type(data) == "table" then data.inputs_sha else nil
		if type(sha) == "string" and #sha == 16 and string.match(sha, "^[0-9a-f]+$") then
			text ..= "\n#pack\n" .. sha
		end
	end
	return string.sub(serde.hash("sha256", text), 1, 16)
end

-- the kit's own calibration builds (kit/grading/scripts): their grades carry this project name
local KIT_SET = "Parallax/grading"

-- the code that MEASURES a build and FITS the weights: a project whose copy differs from the kit home's (it lags, or
-- leads) would write a second measuring code into every project's grades / weights
local MEASURING =
	{ "kit/blender/rbx_score.py", "kit/blender/rbx_quality.py", "kit/blender/rbx_image.py", "kit/blender/rbx.py" }

-- may this project write into the kit home's grades / weights / anchors? -> (problem, what to do) or nil
local function homeCheck(writing: boolean): (string?, string?)
	local problem = Learn.homeProblem()
	if problem then
		return problem, "fix kit/HOME (the kit home's folder), or re-run kit install from the home"
	end
	local home = Learn.home()
	if writing and home ~= "" then
		local differ = {}
		for _, f in MEASURING do
			if scriptSha(f) ~= scriptSha(`{home}/{f}`) then
				table.insert(differ, f)
			end
		end
		if #differ > 0 then
			return `this project's kit measures differently from the kit home's ({table.concat(differ, ", ")} differ)`,
				`update this project's kit first — in {home}: lune run kit install {process.cwd} --update`
		end
	end
	return nil, nil
end

-- re-take the measurements of every graded build this project can rebuild — the kit's own blind-round scripts
-- (kit/grading/scripts) and this project's models — so the grades follow the measuring code. A grade is matched on
-- (asset, project, script sha) and rebuilt only from the SAME script the owner graded; a rebuild that is no longer the
-- model the owner saw (its fingerprint: triangles, size) keeps its old measurements. The owner's numbers and notes
-- never change. -> (re-measured, not re-measured here + why)
local function remeasure(): (number, { string })
	local grades = serde.decode("json", fs.readFile(canonical("grades.json")))
	local here = projectName()
	local hist = Config.path("build") .. "/grading/models"
	local rebuilt, missing = {}, {}
	for _, g in grades do
		if type(g) == "table" and type(g.components) == "table" and type(g.asset) == "string" then
			local script = if g.project == KIT_SET
				then `kit/grading/scripts/{g.asset}.py`
				elseif g.project == here then `{Config.path("models")}/build_{g.asset}.py`
				else nil
			local sha = if script then buildSha(script) else nil
			if not script then
				table.insert(missing, `{g.asset} ({g.project or "?"}: another project)`)
			elseif not sha then
				table.insert(missing, `{g.asset} (its script is gone)`)
			elseif g.script_sha and g.script_sha ~= sha then
				table.insert(missing, `{g.asset} (its script changed since the owner graded it)`)
			else
				local file = `{hist}/{g.asset}.quality.json`
				local before = 0
				if fs.isFile(file) then
					local e = serde.decode("json", fs.readFile(file))
					before = (e[#e] and e[#e].iteration) or 0
				end
				Run.expectingFailure = true -- (graded builds may fail their gates: only their measurements matter here)
				Run.content(
					`remeasure {g.asset}`,
					Run.tool("blender"),
					{ "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", "--no-preview" },
					{ KIT_BUILD = Config.path("build") .. "/grading" }
				)
				Run.expectingFailure = false
				local after = 0
				if fs.isFile(file) then
					local e = serde.decode("json", fs.readFile(file))
					after = (e[#e] and e[#e].iteration) or 0
				end
				if after > before then -- (a new measurement, never the last build's left-over)
					table.insert(rebuilt, `{g.asset}@{g.project}@{g.script_sha or ""}`)
				else
					table.insert(missing, `{g.asset} (the build crashed)`)
				end
			end
		end
	end
	local refreshed = 0
	if #rebuilt > 0 then
		local args = { "kit/blender/rbx_score.py", "refresh", canonical("grades.json"), hist }
		for _, a in rebuilt do
			table.insert(args, a)
		end
		local step = Run.content("grades refresh", Run.tool("python"), args)
		local r = step.result or {}
		refreshed = #(r.refreshed or {})
		for _, c in r.changed or {} do
			table.insert(missing, `{c}: not the build the owner graded any more — ask them to grade it again`)
		end
		syncFromHome("grades.json")
	end
	return refreshed, missing
end

-- a BLIND ROUND the owner graded on a page (kit/grading/README.md) -> the canonical grades. The round file names its
-- SOURCE (the page): every imported grade carries it, so a grade can always be checked against where the owner gave
-- it. { "source": "<the page>", "grades": [ { "asset", "owner", "script_sha", "tris", "note"?, "object"?,
-- "project"? } ] } — script_sha / tris, written when the page was made, prove the build measured is the build shown
-- (the sha the BUILD recorded when it was made). Like `kit grade`, it is the OWNER's act: confirmed at their terminal.
-- A source already imported, or an asset twice in one round, is refused. -> (grades imported) | (nil, why)
-- the build a round's page SHOWED is the build measured: its last history entry made by the same script (the sha the
-- build recorded), measured by today's measuring code, with the triangles the page showed. -> (entry, sha) | (nil, nil, why)
local function shownBuild(asset: string, project: string, shownSha: any, shownTris: any): (any?, string?, string?)
	local here, mv = projectName(), measureVersion()
	local script, hist
	if project == KIT_SET then
		script, hist = `kit/grading/scripts/{asset}.py`, `{Config.path("build")}/grading/models/{asset}.quality.json`
	elseif project == here then
		script, hist = `{Config.path("models")}/build_{asset}.py`, Config.build("models") .. `/{asset}.quality.json`
	else
		return nil, nil, `{asset}: graded in {project} — import it there`
	end
	local e = if fs.isFile(hist) then serde.decode("json", fs.readFile(hist)) else {}
	local last = e[#e]
	local sha = if last then last.script_sha else nil -- (the script that MADE the build, written when it was built)
	if not last or type(last.components) ~= "table" or last.measure ~= mv or not sha then
		return nil, nil, `{asset}: no build measured by today's measuring code — rebuild it`
	elseif shownSha ~= sha or buildSha(script) ~= sha then
		return nil, nil, `{asset}: its last build was not made by the script the round's page showed`
	elseif
		type(shownTris) ~= "number"
		or not last.tris
		or math.abs(last.tris - shownTris) > 0.05 * math.max(shownTris, 1)
	then
		return nil, nil, `{asset}: its last build ({last.tris} triangles) is not the one shown ({tostring(shownTris)})`
	end
	return last, sha, nil
end

local function importRound(file: string?): (number?, string?)
	if not file or not fs.isFile(file) then
		return nil, "--import needs the round's file (kit/grading/README.md: how a page's grades are saved)"
	end
	local ok, round = pcall(serde.decode, "json" :: any, fs.readFile(file))
	if not ok or type(round) ~= "table" or type(round.grades) ~= "table" then
		return nil, `{file} is not a round (a "source" and a list of "grades")`
	end
	if type(round.source) ~= "string" or round.source == "" then
		return nil, `{file} names no source — where the owner gave these grades (the round's page)`
	end
	local okG, existing = pcall(serde.decode, "json" :: any, fs.readFile(canonical("grades.json")))
	for _, g in if okG and type(existing) == "table" then existing else {} do
		if type(g) == "table" and g.source == round.source then
			return nil, `{round.source} was imported already — a round comes in once`
		end
	end
	local here = projectName()
	local entries, problems, seen = {}, {}, {}
	for _, r in round.grades do
		local asset, owner = r.asset, tonumber(r.owner)
		local project = if type(r.project) == "string" then r.project else here
		if type(asset) ~= "string" or not owner or owner < 0 or owner > 100 then
			table.insert(problems, `{tostring(asset)}: needs an asset and a 0-100 owner score`)
			continue
		end
		if seen[`{project}/{asset}`] then
			table.insert(problems, `{asset}: twice in one round`)
			continue
		end
		seen[`{project}/{asset}`] = true
		if type(r.script_sha) ~= "string" or type(r.tris) ~= "number" then
			table.insert(problems, `{asset}: the round must say which build was shown (script_sha and tris)`)
			continue
		end
		local last, sha, why = shownBuild(asset, project, r.script_sha, r.tris)
		if not last then
			table.insert(problems, why)
		else
			table.insert(entries, {
				asset = asset,
				object = r.object,
				project = project,
				raw = last.raw or last.score,
				owner = owner,
				tier = last.tier or "prop",
				components = last.components,
				measure = last.measure,
				script_sha = sha,
				tris = last.tris,
				size = last.size,
				note = `owner (blind grading page): {r.note or ""}`,
				blind = true,
				source = round.source,
				at = Board.now(),
			})
		end
	end
	if #problems > 0 then
		return nil, `nothing imported — {#problems} grade(s) cannot be: {table.concat(problems, "; ")}`
	end
	local confirmed, why = Owner.confirm(
		`OWNER: import {#entries} blind grade(s) from {round.source} (they recalibrate every project's quality scale)`,
		tostring(#entries)
	)
	if not confirmed then
		return nil, `{why} — the owner imports their round: lune run kit grades --import {file}`
	end
	local tmp = Config.build("grading") .. "/_round_entries.json"
	Config.ensureDir(Config.build("grading"))
	fs.writeFile(tmp, serde.encode("json", entries))
	local added = Run.content(
		"grades import",
		Run.tool("python"),
		{ "kit/blender/rbx_score.py", "add", canonical("grades.json"), tmp }
	)
	pcall(fs.removeFile, tmp)
	if not added.ok then
		return nil, (added.result or {}).summary or "the grades file could not be written"
	end
	syncFromHome("grades.json")
	return #entries, nil
end

-- an "A or B?" round (kit/grading/pairs.py page): the owner picked the better of two builds, pair by pair.
-- { "source": "<the page>", "pairs": [ { "a": {asset, project?, script_sha, tris}, "b": {...}, "winner": "a"|"b"|"tie",
-- "margin": 1|2, "note"? } ] } — every side must be the build the page showed (shownBuild). The OWNER's act, confirmed at
-- their terminal; a source comes in once. -> kit/pairs.json (pairs.py agree / strengths read it). -> (pairs) | (nil, why)
local function importPairs(file: string?): (number?, string?)
	if not file or not fs.isFile(file) then
		return nil, "--import-pairs needs the round's file (the A-or-B page's download: kit/grading/README.md)"
	end
	local ok, round = pcall(serde.decode, "json" :: any, fs.readFile(file))
	if not ok or type(round) ~= "table" or type(round.pairs) ~= "table" or type(round.source) ~= "string" then
		return nil, `{file} is not an A-or-B round (a "source" and a list of "pairs")`
	end
	local target = canonical("pairs.json")
	local okP, existing = pcall(serde.decode, "json" :: any, if fs.isFile(target) then fs.readFile(target) else "[]")
	existing = if okP and type(existing) == "table" then existing else {}
	for _, e in existing do
		if type(e) == "table" and e.source == round.source then
			return nil, `{round.source} was imported already — a round comes in once`
		end
	end
	local here = projectName()
	local entries, problems = {}, {}
	for i, r in round.pairs do
		local sides = {}
		for _, k in { "a", "b" } do
			local sd = type(r) == "table" and r[k]
			if type(sd) ~= "table" or type(sd.asset) ~= "string" then
				table.insert(problems, `pair {i}: side {k} names no asset`)
				continue
			end
			local project = if type(sd.project) == "string" then sd.project else here
			local last, sha, why = shownBuild(sd.asset, project, sd.script_sha, sd.tris)
			if not last then
				table.insert(problems, `pair {i}: {why}`)
				continue
			end
			sides[k] = {
				asset = sd.asset,
				project = project,
				script_sha = sha,
				tris = last.tris,
				raw = last.raw or last.score,
			}
		end
		local winner, margin = r.winner, tonumber(r.margin) or 1
		if winner ~= "a" and winner ~= "b" and winner ~= "tie" then
			table.insert(problems, `pair {i}: winner must be "a", "b" or "tie"`)
		elseif margin ~= 1 and margin ~= 2 then
			table.insert(problems, `pair {i}: margin must be 1 or 2`)
		elseif sides.a and sides.b then
			table.insert(entries, {
				a = sides.a,
				b = sides.b,
				winner = winner,
				margin = margin,
				note = if type(r.note) == "string" then r.note else "",
				source = round.source,
				at = Board.now(),
			})
		end
	end
	if #problems > 0 then
		return nil, `nothing imported — {#problems} problem(s): {table.concat(problems, "; ")}`
	end
	if #entries == 0 then
		return nil, `{file} holds no answered pair`
	end
	local confirmed, why = Owner.confirm(
		`OWNER: import {#entries} A-or-B pick(s) from {round.source} (they test the quality score against your eye)`,
		tostring(#entries)
	)
	if not confirmed then
		return nil, `{why} — the owner imports their round: lune run kit grades --import-pairs {file}`
	end
	for _, e in entries do
		table.insert(existing, e)
	end
	fs.writeFile(target, serde.encode("json", existing, true))
	syncFromHome("pairs.json")
	return #entries, nil
end

local function newest(paths: { string }): (any?, number)
	local best, bestTime = nil, -1
	for _, p in paths do
		if fs.isFile(p) then
			local t = fs.metadata(p).modifiedAt
			local ms = if t then t.unixTimestampMillis else 0
			if ms > bestTime then
				local ok, data = pcall(serde.decode, "json", fs.readFile(p))
				if ok then
					best, bestTime = data, ms
				end
			end
		end
	end
	return best, bestTime
end

-- kind -> source file in this project + the verdicts that prove it
local function source(kind: string, name: string): (string?, { string })
	local P = Config.load().paths
	if kind == "asset" then
		return `{P.models}/build_{name}.py`, { `.verify/asset-{name}.json`, ".verify/asset-all.json" }
	elseif kind == "sound" then
		return `{P.sounds}/{name}.json`, { `.verify/sfx-{name}.json`, ".verify/sfx-all.json" }
	elseif kind == "vfx" then
		return `{P.vfx}/{name}.json`, { ".verify/vfx.json" }
	elseif kind == "screen" then
		return `{P.ui}/{name}.json`, { ".verify/ui.json" }
	elseif kind == "world" then
		return `{P.worlds}/{name}.json`, { ".verify/world.json" }
	elseif kind == "anim" then
		return `{P.anims}/{name}.json`, { ".verify/anim.json" }
	end
	return nil, {}
end

local function setAbout(root: string, kind: string, name: string, about: string)
	local path = Library.starter(if root == "" then nil else root) .. "/library.json"
	local index = Library.index(if root == "" then nil else root)
	index[kind] = index[kind] or {}
	index[kind][name] = about
	fs.writeFile(path, serde.encode("json", index, true) .. "\n")
end

function Learn.register(Cli: any)
	-- enforced learning, rule 2 (board/plans/archive/2026-11-09-enforced-learning-plan.md): a new vfx / ui / anim / sfx / world
	-- piece answers the lessons ranked for it before it counts as made (kit verify's quality locks refuse it until then)
	Cli.command(
		"work",
		"answer",
		"answer <vfx|ui|anim|sfx|world> <name> [--show | --reroute]",
		"write the lessons sheet ranked for a new piece (beside its file), then check your answers: the quality locks refuse a new piece until they pass (3D: kit study <asset> --new)",
		function(rawArgs)
			local Answers = require("../lib/answers")
			local LaneLocks = require("../lib/lanelocks")
			local lane = Vault.dept(rawArgs[1])
			local name = rawArgs[2]
			if
				not lane
				or not table.find(LaneLocks.LESSON_LANES, lane)
				or not name
				or string.sub(name, 1, 2) == "--"
			then
				return Run.report(
					"answer",
					{},
					C.USAGE,
					"answer: which lane and which piece?",
					"lune run kit answer <vfx|ui|anim|sfx|world> <name> [--show]   (3D answers its lessons in lune run kit study <asset> --new)"
				)
			end
			local dir = LaneLocks.pieceDir(lane, name)
			if not dir then
				return Run.report(
					"answer",
					{},
					C.USAGE,
					`answer: no {lane} piece named {name} (the project root or a games/<Name>/)`,
					"make the piece first, then answer the lessons ranked for it"
				)
			end
			local command = `lune run kit answer {lane} {name}`
			local path = LaneLocks.sheetPath(dir, name)
			local show = table.find(rawArgs, "--show") ~= nil
			-- the piece's route now (kit/tools/lanecheck.py): the sheet is answered for it, and its words rank its lessons
			local routeNow, routeWords = {}, ""
			do
				local res =
					process.exec(Run.tool("python"), { "kit/tools/lanecheck.py", "route", lane, name, "--dir", dir })
				local okR, v = pcall(serde.decode, "json" :: any, string.match(res.stdout, "([^\n]+)%s*$") or "")
				if res.ok and okR and type(v) == "table" then
					routeNow = if type(v.route) == "table" then v.route else {}
					routeWords = if type(v.words) == "string" then v.words else ""
				end
			end
			if table.find(rawArgs, "--reroute") then
				-- the piece is made a new way (its build refused it): the answers for the old route are kept to read under
				-- "## Earlier answers" (never counted, never to be copied) and every lesson ranked for the NEW route is asked
				if not fs.isFile(path) then
					return Run.report("answer", {}, C.USAGE, `answer {lane} {name}: no sheet to reroute yet`, command)
				end
				local e = Answers.entry(path)
				local was = if e and type(e.route) == "table" then table.concat(e.route, ", ") else "unrecorded"
				if e and type(e.route) == "table" and table.concat(e.route, ",") == table.concat(routeNow, ",") then
					return Run.report(
						"answer",
						{},
						C.USAGE,
						`answer {lane} {name}: its route ({was}) is the one its lessons were answered for - nothing to answer again`,
						command
					)
				end
				local text, ids, must = Answers.sheet(lane, name, command, nil, routeWords)
				local old = fs.readFile(path)
				local body = string.match(old, "## Lessons applied(.*)$") or old
				body = string.gsub(body, "<!%-%-%s*ANSWER", "<!-- earlier")
				local now = if #routeNow > 0 then table.concat(routeNow, ", ") else "none"
				fs.writeFile(
					path,
					text
						.. `\n## Earlier answers (route: {was}, before {Vault.today()})\n\n`
						.. "(answered for the earlier route: kept to read, never counted - answer each lesson above for the new one)\n"
						.. body
				)
				Answers.start(path, lane, name, must, routeNow)
				return Run.report(
					"answer",
					{},
					C.PASS,
					`answer {lane} {name}: rerouted ({was} -> {now}): {#ids} ranked lesson(s), {#must} to answer again for the new route -> {path}`,
					`answer each for the NEW route (a copied old answer does not count), then: {command}`
				)
			end
			if show or not fs.isFile(path) then
				local text, ids, must = Answers.sheet(lane, name, command, nil, routeWords)
				for line in string.gmatch(text, "[^\n]+") do
					if
						string.find(line, "<!-- ANSWER", 1, true)
						or (show and string.find(line, "<!-- optional", 1, true))
					then
						print("  " .. string.gsub(string.gsub(line, "^<!%-%- ", ""), " %-%->$", ""))
					end
				end
				if show then
					return Run.report(
						"answer",
						{},
						C.PASS,
						`answer {lane} {name}: {#ids} lesson(s) ranked for it (shown; nothing written)`,
						command
					)
				end
				fs.writeFile(path, text)
				Answers.start(path, lane, name, must, routeNow)
				return Run.report(
					"answer",
					{},
					C.PASS,
					`answer {lane} {name}: the sheet of {#ids} ranked lesson(s), {#must} to answer -> {path}`,
					if #must > 0
						then `answer each of the {#must} ANSWER lessons in {path} ("- <id>: how this piece applies it" or "- skip <id>: why not", 6+ words), then: {command}`
						else `no lesson shares two words with this piece: apply an optional one or write "- none: <why>" in {path}, then: {command}`
				)
			end
			-- a sheet with no record (written by hand, or its record lost): its lessons to answer are ranked again and kept
			if not Answers.entry(path) then
				local _, _, must = Answers.sheet(lane, name, command, nil, routeWords)
				Answers.start(path, lane, name, must, routeNow)
				print(`  no record of this sheet's lessons: {#must} ranked again now and kept in board/answers.json`)
			end
			local sheet = fs.readFile(path)
			local r = Answers.check(sheet, lane, path)
			if #r.problems > 0 then
				for _, p in r.problems do
					print(`  {p}`)
				end
				return Run.report(
					"answer",
					{},
					C.CONTENT,
					`answer {lane} {name}: {#r.problems} to answer before it counts as made`,
					`answer them in {path}, then: {command}`
				)
			end
			local recorded = Answers.record(lane, name, r.applied)
			Answers.passed(path, lane, name, sheet, r)
			return Run.report(
				"answer",
				{},
				C.PASS,
				`answer {lane} {name}: {#r.applied} applied, {#r.skipped} skipped{if recorded
					then " - the applied ones recorded on " .. name .. " (the owner's verdict on it credits or flags each)"
					else ""}`,
				`commit {path}, board/answers.json and board/citations.json`
			)
		end
	)
	-- the owner's words on a piece's time budget (card b6m2: "Yes, same budgets" - every lane on 3D's tiers): past it a
	-- lane builds no change to the piece until he gives more minutes or a new attempt (kit/tools/lanecheck.py; 3D: kit plan)
	Cli.command(
		"work",
		"clock",
		'clock <vfx|ui|anim|sfx|world|3d> <name> --extend <minutes> "<the owner words>" | --restart "<the owner words>"',
		"the owner's words on a piece's time budget: more minutes on this attempt, or a new attempt (only his words: past the budget a lane builds no change to the piece)",
		function(rawArgs)
			local LaneLocks = require("../lib/lanelocks")
			local lane, name = Vault.dept(rawArgs[1]) or rawArgs[1], rawArgs[2]
			local k = table.find(rawArgs, "--extend")
			local r = table.find(rawArgs, "--restart")
			if not lane or not name or string.sub(name, 1, 2) == "--" or (not k and not r) then
				return Run.report(
					"clock",
					{},
					C.USAGE,
					"clock: which lane, which piece, and the owner's words?",
					'lune run kit clock <lane> <name> --extend <minutes> "<the owner words>"   (or --restart "<the owner words>")'
				)
			end
			if lane == "3d" then -- (3D keeps its clock in kit plan)
				local argv = { "kit/tools/plan.py", name }
				if k then
					table.insert(argv, "--extend")
					table.insert(argv, rawArgs[k + 1] or "")
					table.insert(argv, rawArgs[k + 2] or "")
				else
					table.insert(argv, "--restart")
					table.insert(argv, rawArgs[(r :: number) + 1] or "")
				end
				local step = Run.content("clock", Run.tool("python"), argv)
				return Run.report(
					"clock",
					{ step },
					if step.ok then C.PASS else C.USAGE,
					if step.ok then `clock 3d {name}: done on the owner's words` else "clock 3d: refused",
					`lune run kit plan {name}`
				)
			end
			local dir = LaneLocks.pieceDir(lane, name)
			if not dir then
				return Run.report("clock", {}, C.USAGE, `clock: no {lane} piece named {name}`, "lune run kit status")
			end
			name = require("../lib/prebuild").stem(dir, name) -- (its clock is kept under the name its file spells)
			local argv = { "kit/tools/lanecheck.py" }
			if k then
				for _, a in { "extend", lane, name, rawArgs[k + 1] or "", rawArgs[k + 2] or "" } do
					table.insert(argv, a)
				end
			else
				for _, a in { "restart", lane, name, rawArgs[(r :: number) + 1] or "" } do
					table.insert(argv, a)
				end
				if require("../lib/prebuild").heroOk(lane, name) then -- (the new attempt's tier: the spec's, in lanecheck)
					table.insert(argv, "--hero-ok")
				end
			end
			table.insert(argv, "--dir")
			table.insert(argv, dir)
			local step = Run.content("clock", Run.tool("python"), argv)
			local res = step.result or {}
			return Run.report(
				"clock",
				{ step },
				if step.ok then C.PASS else C.USAGE,
				res.summary or "clock: crashed",
				res.next_action or "read the error above"
			)
		end
	)
	Cli.command(
		"work",
		"lesson",
		'lesson <area> "what you learned" [--gist "the fix in one line"] [--stage <stage>[,<stage>]] [--family <family>] [--as model@harness] | lesson used <id,...> --piece <kind> <name>',
		"record a non-obvious lesson for every future session in every project (at most 1,200 characters; --gist = its one-line fix, shown when it ranks below the top two); `lesson used` names the lessons you applied to a piece (the owner's verdict on it credits them)",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			-- the lessons a session applied to one piece: the owner's later verdict on it moves their counters
			if args[1] == "used" then
				local ids, name = {}, args[3]
				for id in string.gmatch(args[2] or "", "[^,%s]+") do
					table.insert(ids, id)
				end
				local kind = if type(flags.piece) == "string" then flags.piece else nil
				if #ids == 0 or not kind or not name then
					return Run.report(
						"lesson",
						{},
						C.USAGE,
						"lesson used: name the lesson ids (from kit start / kit help --stage) and the piece",
						"lune run kit lesson used L-3d-a1b2c3,L-3d-d4e5f6 --piece asset barrel"
					)
				end
				for _, id in ids do
					if not Vault.lessonById(id) and not Vault.ruleById(id) then
						return Run.report(
							"lesson",
							{},
							C.USAGE,
							`lesson used: no lesson has the id {id}`,
							`copy the ids shown in brackets by lune run kit start <lane> / kit lessons <area> --stage <stage>`
						)
					end
				end
				local ok, err = Vault.cite(kind, name, ids, Board.agent(flags.as))
				if not ok then
					return Run.report(
						"lesson",
						{},
						C.USAGE,
						`lesson used: {err}`,
						"kinds: asset vfx screen sound world anim"
					)
				end
				return Run.report(
					"lesson",
					{},
					C.PASS,
					`lesson used: {#ids} lesson(s) cited on {kind} {name} ({Vault.citationsPath()})`,
					`when the owner scores {name}, each cited lesson is credited (7+ helpful, 3- harmful); commit {Vault.citationsPath()}`
				)
			end
			local area, text = args[1], table.concat(args, " ", 2)
			if not area or not Learn.AREAS[area] or text == "" then
				local names = {}
				for k in Learn.AREAS do
					table.insert(names, k)
				end
				table.sort(names)
				return Run.report(
					"lesson",
					{},
					C.USAGE,
					"lesson: needs a known area and the lesson text",
					`lune run kit lesson <{table.concat(names, "|")}> "booleans: cutters must overlap the part clearly"`
				)
			end
			-- one lesson, one fix: a longer text is two lessons (it is printed whole when it ranks first; Vault.LESSON_MAX)
			local chars = utf8.len(text) or #text
			if chars > Vault.LESSON_MAX then
				return Run.report(
					"lesson",
					{},
					C.USAGE,
					`lesson: {chars} characters - at most {Vault.LESSON_MAX}; it holds more than one lesson`,
					`split it: one kit lesson {area} "..." per fix, each with its own --gist`
				)
			end
			local gist = if type(flags.gist) == "string" then flags.gist else nil
			if gist and (utf8.len(gist) or #gist) > 160 then
				return Run.report(
					"lesson",
					{},
					C.USAGE,
					"lesson: --gist is one line, at most 160 characters",
					`lune run kit lesson {area} "..." --gist "<the fix, in a line>"`
				)
			end
			local problem = Learn.homeProblem()
			if problem then
				return Run.report("lesson", {}, C.USAGE, "lesson: the kit home is missing", problem)
			end
			local line = `- {string.sub(Board.now(), 1, 10)} ({Board.agent(flags.as)}, {projectName()}): {text}`
			local home = Learn.home()
			-- the vault note (the record every harness reads; kit status / kit new print the department page)
			local dept = Vault.dept(area)
			-- --stage a,b: the stage(s) of the route this lesson is for (kit help --stage shows it there); without it
			-- the stage is read from the lesson's words
			local stages: { string }? = nil
			if type(flags.stage) == "string" and dept then
				local known = Routes.stages(dept)
				stages = {}
				for s in string.gmatch(flags.stage, "[^,%s]+") do
					if not table.find(known, s) then
						return Run.report(
							"lesson",
							{},
							C.USAGE,
							`lesson: "{s}" is not a {dept} stage ({table.concat(known, ", ")})`,
							`lune run kit lesson {area} "..." --stage {known[1] or "<stage>"}`
						)
					end
					table.insert(stages :: { string }, s)
				end
			end
			-- --family <name>: the lesson's family by hand (kit/knowledge/families.json; else its words decide - sprint 5)
			local family: string? = nil
			if type(flags.family) == "string" and dept then
				local names = require("../lib/families").names(dept)
				if not table.find(names, flags.family) then
					return Run.report(
						"lesson",
						{},
						C.USAGE,
						`lesson: "{flags.family}" is not a {dept} family ({if #names > 0
							then table.concat(names, ", ")
							else "this lane has none"})`,
						`lune run kit lesson {area} "..." --family {names[1] or "<family>"}`
					)
				end
				family = flags.family
			end
			-- written only now: a mistyped --stage or --family refused above leaves no half-written lesson behind
			append(lessonFile(home, area), Learn.AREAS[area], line)
			local where = if home == "" then "kit/lessons (this is the kit's home)" else `the kit home ({home})`
			if dept and Vault.exists() then
				local date = string.sub(Board.now(), 1, 10)
				local notePath = Vault.note(dept, "lessons", `{date}-{Vault.slug(text)}`, {
					kind = "lesson",
					area = dept,
					date = date,
					by = Board.agent(flags.as),
					project = projectName(),
					source = "kit lesson",
					stages = stages,
					gist = gist,
					family = family,
				}, text)
				where ..= " + the vault"
				-- a new lesson changes what the lane's creative director knows: it re-learns by itself (sprint 3)
				local relearned = require("../lib/directors").relearn(dept, Vault.dir(dept))
				if relearned then
					print(`  {relearned}`)
				end
				-- --verdict <name>: this lesson is what the owner's verdict on <name> taught (enforced learning, rule 1)
				if type(flags.verdict) == "string" and flags.verdict ~= "" then
					local id = Vault.lessonId({
						path = notePath,
						rel = string.sub(notePath, #Vault.ROOT + 2, -4),
						front = { area = dept },
						body = "",
					} :: any)
					-- every verdict on the piece that still owes (the lesson is what each taught), else its newest one
					local targets: { Vault.Note } = {}
					for _, v in Vault.owedLearning(dept) do
						if string.lower(tostring(v.front.name)) == string.lower(flags.verdict) then
							table.insert(targets, v)
						end
					end
					if #targets == 0 then
						local newestOne = Vault.verdicts(dept, flags.verdict)[1]
						if newestOne then
							table.insert(targets, newestOne)
						end
					end
					if #targets > 0 then
						for _, target in targets do
							local ok, err = Vault.markLearned(target, { id }, nil)
							print(
								if ok
									then `  {id} paid what the verdict {target.rel} taught`
									else `  could not mark {target.rel} learned: {err}`
							)
						end
						print(`  {#Vault.owedLearning(dept)} still owed in {dept}`)
					else
						print(
							`  no {dept} verdict on {flags.verdict} to pay with {id} (lune run kit verdict owed {dept})`
						)
					end
				end
			end
			if home ~= "" then
				append(Board.dir(`lessons/{area}.md`), Learn.AREAS[area], line)
				where ..= " + board/lessons"
			end
			local lessonNextAction = if home ~= ""
				then "commit board/; other projects get it on their next `kit sync`"
				elseif
					fs.isFile("kit/UPSTREAM.json")
				then "commit kit/lessons locally; to share upstream open a pull request at https://github.com/mayusi/parallax"
				else "commit kit/lessons; projects get it on their next `kit update` / `kit sync`"
			return Run.report("lesson", {}, C.PASS, `lesson: recorded for {area} in {where}`, lessonNextAction)
		end
	)

	-- the OWNER grades an asset: the kit's raw score is refitted to the owner's eye (kit/grades.json in the kit
	-- home, copied into every project by kit update/sync). A grade is the owner's alone: it is confirmed with their own
	-- keystrokes at a real terminal (kit/lib/owner.luau) — a model can start this command in their terminal, never
	-- finish it. Blind rounds graded on a page come in through `kit grades --import`, each grade naming its page.
	Cli.command(
		"work",
		"grade",
		'grade <asset> <0-100> ["what is wrong / right"]',
		"the OWNER's score for a built asset (confirmed at their terminal) — recalibrates the quality scale everywhere",
		function(rawArgs)
			local args = Cli.parse(rawArgs)
			local asset, score = args[1], tonumber(args[2])
			if not asset or not score or score < 0 or score > 100 then
				return Run.report(
					"grade",
					{},
					C.USAGE,
					"grade: needs an asset name and a 0-100 score",
					'lune run kit grade orbital_sniper 80 "detail is shallow, panels lack layering"'
				)
			end
			local problem, fix = homeCheck(true)
			if problem then
				return Run.report("grade", {}, C.USAGE, `grade: {problem}`, fix or "read the problem above")
			end
			local hist = Config.build("models") .. `/{asset}.quality.json`
			if not fs.isFile(hist) then
				return Run.report(
					"grade",
					{},
					C.USAGE,
					`grade: {asset} has no quality history`,
					`build it first: lune run kit asset {asset}`
				)
			end
			local entries = serde.decode("json", fs.readFile(hist))
			local last = entries[#entries]
			if last.measure ~= measureVersion() or not last.script_sha then -- a grade carries what TODAY's code sees
				return Run.report(
					"grade",
					{},
					C.USAGE,
					`grade: {asset}'s last build was measured by other measuring code (measure {last.measure or "none"}, the kit's is {measureVersion() or "?"})`,
					`rebuild it first (the same build the owner looked at): lune run kit asset {asset}`
				)
			end
			local raw = last.raw or last.score
			-- the measured components + tier travel with the grade: a later change of weights re-scores this grade
			-- too (rbx_quality.raw_of), instead of leaving a stale raw number in the calibration
			local manifest = Config.build("models") .. `/{asset}.manifest.json`
			local tier = "prop"
			if fs.isFile(manifest) then
				local ok, m = pcall(serde.decode, "json" :: any, fs.readFile(manifest))
				if ok and m and m.facts and m.facts.quality and m.facts.quality.tier then
					tier = m.facts.quality.tier
				end
			end
			local entry = {
				asset = asset,
				project = projectName(),
				raw = raw,
				owner = score,
				tier = tier,
				components = last.components,
				measure = last.measure, -- (which measuring code saw these components: rbx_score.MEASURE_VERSION)
				-- the script that MADE the build the owner judged (written into its history when it was built): a
				-- later re-measure rebuilds exactly this one, or refuses
				script_sha = last.script_sha,
				-- the build's fingerprint: a re-measure that finds another model (the kit changed under the script)
				-- leaves this grade alone
				tris = last.tris,
				size = last.size,
				note = table.concat(args, " ", 3),
				at = Board.now(),
			}
			local confirmed, why = Owner.confirm(
				`OWNER: grade {asset} {score}/100 (it recalibrates every project's quality scale)`,
				tostring(score)
			)
			if not confirmed then
				return Run.report(
					"grade",
					{},
					C.USAGE,
					`grade: {why}`,
					`the owner grades: they run  lune run kit grade {asset} {score} "..."  in their own terminal, or grade a blind round page (kit/grading/README.md) that is imported with  lune run kit grades --import <round.json>`
				)
			end
			local wrote = {}
			-- appended to the CANONICAL grades (the kit home's: every project's), then copied down to this project
			local tmp = Config.build("grading") .. "/_grade_entry.json"
			Config.ensureDir(Config.build("grading"))
			fs.writeFile(tmp, serde.encode("json", entry))
			local added = Run.content(
				"grade add",
				Run.tool("python"),
				{ "kit/blender/rbx_score.py", "add", canonical("grades.json"), tmp }
			)
			pcall(fs.removeFile, tmp)
			if not added.ok then
				return Run.report("grade", { added }, C.CONTENT, "grade: could not record it", "read the error above")
			end
			syncFromHome("grades.json")
			table.insert(wrote, canonical("grades.json"))
			-- the graded render becomes an ANCHOR every judge packet shows: kept in the kit home's anchors (every
			-- project's, each anchor named by its project), then copied down
			local anchorStep = Run.content(
				"anchor",
				Run.tool("python"),
				{ "kit/blender/judge.py", "anchor", asset, tostring(score), entry.note },
				{ KIT_ANCHORS = canonical("anchors"), KIT_PROJECT = projectName() }
			)
			if anchorStep.ok then
				syncDirFromHome("anchors")
				table.insert(wrote, canonical("anchors"))
			end
			-- the ONE verdict record (kit/knowledge/vault/3d/verdicts): a grade is an owner verdict on the 0-100 scale
			if Vault.exists() then
				local okV, path = pcall(Vault.record, {
					kind = "asset",
					name = asset,
					score = math.floor(score + 0.5) / 10,
					words = entry.note or "",
					tags = { "grade", "anchor" },
					by = "owner",
				})
				if okV and path then
					table.insert(wrote, path)
				end
			end
			return Run.report(
				"grade",
				{},
				C.PASS,
				`grade: {asset} raw {raw} -> owner {score}; the quality scale refits on the next build ({table.concat(
					wrote,
					", "
				)})`,
				`rebuild to see the calibrated score: lune run kit asset {asset}`
			)
		end
	)

	-- how well does the score follow the OWNER? Every grade is predicted by weights + calibration fitted WITHOUT it
	-- (leave-one-out): the hand weights vs a refit, then one test per metric (a sign test on same-object pairs,
	-- McNemar on pass / fail, a bootstrap on rank) — and the current weights on FRESH grades (given after they were
	-- fitted: the prospective test). --write keeps a refit only when no test says it is worse (p < .05) and one says it
	-- is better (p < .0914 each: at most one no-better refit in four kept) — in the kit home's weights.json, beside the
	-- grades, copied down to this project.
	-- --import <round.json> brings in a blind round the owner graded on a page.
	Cli.command(
		"work",
		"grades",
		"grades [--fit] [--write] [--lam N] [--remeasure] [--import <round.json>] [--import-pairs <round.json>] [--pairs-page <list.json>]",
		"how well the quality score follows the owner's grades (leave-one-out, and on fresh grades) — refit, import a round",
		function(rawArgs)
			local writing = table.find(rawArgs, "--write") ~= nil
				or table.find(rawArgs, "--remeasure") ~= nil
				or table.find(rawArgs, "--import") ~= nil
				or table.find(rawArgs, "--import-pairs") ~= nil
			local problem, fix = homeCheck(writing)
			if problem then
				return Run.report("grades", {}, C.USAGE, `grades: {problem}`, fix or "read the problem above")
			end
			local imp = table.find(rawArgs, "--import")
			if imp then
				local n, err = importRound(rawArgs[imp + 1])
				if not n then
					return Run.report(
						"grades",
						{},
						C.USAGE,
						`grades: {err}`,
						"fix the round file (kit/grading/README.md), rebuild what it names, import again"
					)
				end
				print(
					`grades: imported {n} blind grade(s) into {canonical("grades.json")} — each names its source page`
				)
			end
			local pp = table.find(rawArgs, "--pairs-page")
			if pp then
				local page = Run.content(
					"pairs page",
					Run.tool("python"),
					{ "kit/grading/pairs.py", "page", rawArgs[pp + 1] or "" }
				)
				local pr = page.result or {}
				return Run.report(
					"grades",
					{ page },
					if page.ok then C.PASS else C.USAGE,
					pr.summary or "pairs page: crashed",
					pr.next_action or "read the error above"
				)
			end
			local ip = table.find(rawArgs, "--import-pairs")
			if ip then
				local n, err = importPairs(rawArgs[ip + 1])
				if not n then
					return Run.report(
						"grades",
						{},
						C.USAGE,
						`grades: {err}`,
						"fix the A-or-B round file (kit/grading/README.md), rebuild what it names, import again"
					)
				end
				print(
					`grades: imported {n} A-or-B pick(s) into {canonical("pairs.json")} — each names its source page`
				)
			end
			if table.find(rawArgs, "--remeasure") then
				local done, missing = remeasure()
				print(
					`grades: re-measured {done} graded build(s){if #missing > 0
						then "; not re-measured here: " .. table.concat(missing, ", ")
						else ""}`
				)
			end
			local args = { "kit/blender/rbx_score.py", "fit" }
			local skip = false
			for _, a in rawArgs do
				if skip then
					skip = false
				elseif a == "--import" or a == "--import-pairs" or a == "--pairs-page" then
					skip = true
				elseif a ~= "--fit" and a ~= "--remeasure" then
					table.insert(args, a)
				end
			end
			-- fitted on the CANONICAL grades (the kit home's: every project's), written to the home's weights, copied down
			local step = Run.content(
				"grades fit",
				Run.tool("python"),
				args,
				{ KIT_GRADES = canonical("grades.json"), KIT_WEIGHTS_OUT = canonical("weights.json") }
			)
			local r = step.result or {}
			local summary = r.summary or "grades: crashed"
			if step.ok and type(r.wrote) == "string" then
				syncFromHome("weights.json")
			end
			-- the owner's A-or-B picks: how often the score (as built, when picked) chose the owner's winner
			if fs.isFile(canonical("pairs.json")) then
				local agree = Run.content(
					"pairs agree",
					Run.tool("python"),
					{ "kit/grading/pairs.py", "agree", canonical("pairs.json") }
				)
				local ar = agree.result or {}
				if agree.ok and type(ar.summary) == "string" then
					summary ..= " · A-or-B: " .. ar.summary
				end
			end
			return Run.report(
				"grades",
				{ step },
				if step.ok then C.PASS else C.CONTENT,
				summary,
				r.next_action or "read the error above"
			)
		end
	)

	Cli.command(
		"work",
		"lessons",
		"lessons [area] [words...] [--stage <stage>] [--all] [--n 25]",
		"what earlier sessions learned: the newest 25 per area, or those naming every word given; --all = every one",
		function(rawArgs)
			-- 3D alone holds 170+ lessons (~21,000 tokens): a model reads the newest, or searches, unless it asks for all
			local args, words, all, limit = {}, {}, false, 25
			local stageWanted: string? = nil
			local i = 1
			while i <= #rawArgs do
				local a = rawArgs[i]
				if a == "--all" then
					all = true
				elseif a == "--stage" then
					stageWanted = rawArgs[i + 1]
					i += 1
				elseif a == "--n" then
					limit = tonumber(rawArgs[i + 1]) or limit
					i += 1
				elseif #args == 0 and (Learn.AREAS[a] or (i == 1 and not string.match(a, "^%-%-"))) then
					table.insert(args, a) -- the area (an unknown first word is reported below)
				elseif not string.match(a, "^%-%-") then
					table.insert(words, string.lower(a))
				end
				i += 1
			end
			local function pick(list: { string }): ({ string }, number)
				local kept = {}
				for _, l in list do
					local low = string.lower(l)
					local hit = true
					for _, w in words do
						if not string.find(low, w, 1, true) then
							hit = false
							break
						end
					end
					if hit then
						table.insert(kept, l)
					end
				end
				if all or #words > 0 then
					return kept, 0
				end
				-- newest first by the lesson's date; the rest are counted, not printed
				local order = {}
				for k, l in kept do
					table.insert(order, { k = k, d = string.match(l, "%d%d%d%d%-%d%d%-%d%d") or "" })
				end
				table.sort(order, function(x, y)
					if x.d ~= y.d then
						return x.d > y.d
					end
					return x.k > y.k
				end)
				local out = {}
				for k = 1, math.min(limit, #order) do
					table.insert(out, kept[order[k].k])
				end
				return out, #kept - #out
			end
			local areas = {}
			if args[1] then
				if not Learn.AREAS[args[1]] then
					return Run.report(
						"lessons",
						{},
						C.USAGE,
						`lessons: unknown area "{args[1]}"`,
						"lune run kit lessons"
					)
				end
				areas = { args[1] }
			else
				for k in Learn.AREAS do
					table.insert(areas, k)
				end
				table.sort(areas)
			end
			-- --stage <stage>: only the lessons of that stage of the area's route (a hand tag, else the lesson's words)
			if stageWanted then
				local dept = #areas == 1 and Vault.dept(areas[1]) or nil
				local known = if dept then Routes.stages(dept) else {}
				if not dept or not table.find(known, stageWanted) then
					return Run.report(
						"lessons",
						{},
						C.USAGE,
						`lessons: --stage needs one area and one of its stages{if dept
							then " (" .. table.concat(known, ", ") .. ")"
							else ""}`,
						"lune run kit lessons 3d --stage surface"
					)
				end
			end
			local total, hidden = 0, 0
			for _, a in areas do
				local list = Learn.lessons(a)
				if stageWanted then
					local dept = Vault.dept(a) :: string
					list = Vault.stageLessons(dept, stageWanted, Routes.words(dept), true)
				end
				local shown, rest
				local dept = Vault.dept(a)
				if #words > 0 and dept and Vault.exists() and not all then
					-- words given: RANKED by relevance (Vault.rank), not "every word appears" - "rust" finds the
					-- corrosion lesson that also says rust once, best first, each in full with its id
					local ranked = Vault.rank(
						dept,
						table.concat(words, " "),
						{ stage = stageWanted, stageWords = if stageWanted then Routes.words(dept) else nil }
					)
					local counts = Vault.lessonCounts()
					local hits = {}
					for _, r in ranked do
						if r.relevance > 0 then
							table.insert(hits, r)
						end
					end
					shown = {}
					for k = 1, math.min(limit, #hits) do
						table.insert(shown, Vault.rankedLine(hits[k], counts, true))
					end
					rest = #hits - #shown
					-- a lesson only the flat files hold (board/lessons/<area>.md in an installed project, never filed
					-- into a vault note): still found, by the old every-word match, after the ranked ones
					if not stageWanted then
						local inVault = {}
						for _, r in ranked do
							local t = string.gsub(string.gsub(r.note.body, "%s+", " "), "^%s+", "")
							inVault[string.gsub(t, "%s+$", "")] = true
						end
						local flatOnly = {}
						for _, l in list do
							local t = string.match(l, "%):%s*(.*)$") or l
							t = string.gsub(string.gsub(string.gsub(t, "%s+", " "), "^%s+", ""), "%s+$", "")
							if not inVault[t] then
								table.insert(flatOnly, l)
							end
						end
						local extra = pick(flatOnly)
						for _, l in extra do
							if #shown < limit then
								table.insert(shown, l)
							else
								rest += 1
							end
						end
					end
				else
					shown, rest = pick(list)
				end
				if #shown > 0 or #areas == 1 then
					print(
						`-- {a}: {Learn.AREAS[a]} ({#shown} of {#list}{if #words > 0
							then ' naming "' .. table.concat(words, " ") .. '"'
							else ""})`
					)
					for _, l in shown do
						print("  " .. l)
					end
					if rest > 0 then
						print(
							if #words > 0
								then `  ... {rest} more, ranked lower: add --n {limit + rest} to see them`
								else `  ... {rest} older: lune run kit lessons {a} <words> (search) or --all`
						)
					end
				end
				total += #shown
				hidden += rest
			end
			return Run.report(
				"lessons",
				{},
				C.PASS,
				if hidden > 0
					then `lessons: {total} shown, {hidden} {if #words > 0 then "ranked lower" else "older"} not printed`
					else `lessons: {total}`,
				'apply the relevant ones; learned something new? lune run kit lesson <area> "..."'
			)
		end
	)

	Cli.command(
		"work",
		"promote",
		'promote <asset|sound|vfx|screen|world|anim> <name> --about "one line" [--force]',
		"add proven content to the example library every project can start from",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local kind, name = args[1], args[2]
			local src, verdicts = source(kind or "", name or "")
			if not src or not name then
				return Run.report(
					"promote",
					{},
					C.USAGE,
					"promote: needs a kind and a name",
					'lune run kit promote asset crate --about "wooden crate with frames and bolts"'
				)
			end
			if not fs.isFile(src) then
				return Run.report("promote", {}, C.USAGE, `promote: {src} does not exist`, "check the name")
			end
			-- proven = its gate passed AFTER the last edit
			local verdict, at = newest(verdicts)
			local edited = fs.metadata(src).modifiedAt
			local editedMs = if edited then edited.unixTimestampMillis else 0
			if not verdict or verdict.status ~= "pass" or at < editedMs then
				return Run.report(
					"promote",
					{},
					C.CONTENT,
					`promote: {kind} {name} has no passing gate since its last edit`,
					`run its command first (e.g. lune run kit {if kind == "asset"
						then "asset " .. name
						elseif kind == "sound" then "sfx " .. name
						elseif kind == "screen" then "ui"
						else kind}) and look at the evidence`
				)
			end
			if kind == "screen" then
				-- an example nobody looked at is a template for the next model's mistakes: the look record must be
				-- of the build that is being promoted (kit ui look <Name> "...")
				local modelPath = `{Config.path("uiOut")}/{name}.model.json`
				local lookPath = `{Config.path("ui")}/{name}.look.json`
				local fresh = false
				if fs.isFile(modelPath) and fs.isFile(lookPath) then
					local okLook, look = pcall(serde.decode, "json" :: any, fs.readFile(lookPath))
					fresh = okLook
						and type(look) == "table"
						and look.model_sha256 == serde.hash("sha256", fs.readFile(modelPath))
				end
				if not fresh then
					return Run.report(
						"promote",
						{},
						C.CONTENT,
						`promote: nobody looked at the current build of {name}`,
						`look at {Config.build("ui")}/{name}.png (desktop, phone, tablet) and {name}.motion.png, then: lune run kit ui look {name} "<what you saw>"`
					)
				end
			end
			-- the OWNER's gate (2026-10-08: "they're all bad" — our own unapproved builds are not reuse material; Voyager:
			-- a skill enters the library only after verified success): an example needs an owner verdict >= 7 in the
			-- vault, or the owner's words quoted with --owner "...".
			if Vault.exists() then
				local score = Vault.scoreOf(kind, name, true) -- the owner's own: an inferred verdict never promotes
				if (not score or score < 7) and type(flags.owner) ~= "string" then
					return Run.report(
						"promote",
						{},
						C.CONTENT,
						`promote: {kind} {name} has no owner verdict >= 7 in the vault ({if score
							then "latest " .. tostring(score) .. "/10"
							else "none recorded"})`,
						`show it to the owner; record their verdict: lune run kit verdict {kind} {name} <0-10> "<their words>"  (or quote them now: --owner "<their words>")`
					)
				end
			end
			if type(flags.about) ~= "string" or flags.about == "" then
				return Run.report(
					"promote",
					{},
					C.USAGE,
					"promote: say what it is and what technique it shows",
					`lune run kit promote {kind} {name} --about "what it is — the technique worth copying"`
				)
			end
			local problem = Learn.homeProblem()
			if problem then
				return Run.report("promote", {}, C.USAGE, "promote: the kit home is missing", problem)
			end
			local home = Learn.home()
			local k = Library.KINDS[kind]
			local targets = { home }
			if home ~= "" then
				-- also this project's kit copy (kit-owned, refreshed from the home anyway) so `kit examples` shows it now
				table.insert(targets, "")
			end
			local starterRecordProblem: string? = nil
			for _, root in targets do
				local dest = `{Library.starter(if root == "" then nil else root)}/{k.dir}/{k.file(name)}`
				if fs.isFile(dest) and not flags.force and root == home then
					return Run.report(
						"promote",
						{},
						C.USAGE,
						`promote: an example named {name} already exists`,
						"pick another name, or --force to replace it (only if yours is better)"
					)
				end
				Config.ensureDir(string.match(dest, "^(.*)/[^/]+$") :: string)
				fs.writeFile(dest, fs.readFile(src))
				setAbout(root, kind, name, flags.about)
				-- an effect travels with its parts, its textures (imported ones as their finished pictures) and their
				-- uploaded ids: it must play in a project that never saw them (kit new vfx X --from <name> copies them back)
				if kind == "vfx" then
					local okSpec, spec = pcall(serde.decode, "json" :: any, fs.readFile(src))
					if okSpec then
						Library.packVfx(Library.starter(if root == "" then nil else root), name, spec, {
							vfx = Config.path("vfx"),
							textures = Config.path("textures"),
							buildTextures = Config.build("textures"),
						})
					end
					-- the kit's record of its starter texts (kit/vfx/starters.py): in the kit's HOME the promoted effect and
					-- its packed pieces are starters from now on, which a new project's gates leave to their first edit;
					-- a project's kit copy keeps the home's record (sync and updates bring it)
					local kitDir = (if root == "" then "" else root .. "/") .. "kit"
					if fs.isFile(kitDir .. "/.source") then
						local step = Run.content(
							"promote starter record",
							Run.tool("python"),
							{ "kit/vfx/starters.py", "--write", "--kit", kitDir }
						)
						if not step.ok then
							starterRecordProblem =
								`the starter record in {kitDir}/vfx/starters.json was not updated ({step.tail})`
						end
					end
				end
				-- a screen travels with its identity pack and that identity's own art (icons, emblems): the example
				-- must compile in a project that never saw them (kit new screen X --from <name> copies them back)
				if kind == "screen" then
					local okSpec, spec = pcall(serde.decode, "json" :: any, fs.readFile(src))
					local id = if okSpec and type(spec) == "table" then spec.identity else nil
					if type(id) == "string" then
						local starter = Library.starter(if root == "" then nil else root)
						local idSrc = `{Config.path("ui")}/identities/{id}.json`
						if fs.isFile(idSrc) then
							Config.ensureDir(`{starter}/ui/identities`)
							fs.writeFile(`{starter}/ui/identities/{id}.json`, fs.readFile(idSrc))
						end
						local artSrc = `{Config.path("ui")}/art/{id}`
						if fs.isDir(artSrc) then
							Config.ensureDir(`{starter}/ui/art/{id}`)
							for _, f in fs.readDir(artSrc) do
								-- the pictures AND how they were made: .render.json / .anchors.json / .trace.json / PROVENANCE.md
								if
									string.sub(f, -4) == ".png"
									or string.sub(f, -5) == ".json"
									or string.sub(f, -3) == ".md"
								then
									fs.writeFile(`{starter}/ui/art/{id}/{f}`, fs.readFile(`{artSrc}/{f}`))
								end
							end
						end
						-- the references' measurements travel too (REFS.md only: the stills are measure-only sources)
						local refsMd = `{Config.path("ui")}/refs/{id}/REFS.md`
						if fs.isFile(refsMd) then
							Config.ensureDir(`{starter}/ui/refs/{id}`)
							fs.writeFile(`{starter}/ui/refs/{id}/REFS.md`, fs.readFile(refsMd))
						end
					end
					-- a gauge screen is generated from its .gauge.json: that is the real source
					local gaugeSrc = `{Config.path("ui")}/{name}.gauge.json`
					if fs.isFile(gaugeSrc) then
						-- (under gauges/: the starter's own ui/*.json are screens, and every one of them must compile)
						local starterRoot = Library.starter(if root == "" then nil else root)
						Config.ensureDir(`{starterRoot}/ui/gauges`)
						fs.writeFile(`{starterRoot}/ui/gauges/{name}.gauge.json`, fs.readFile(gaugeSrc))
					end
					-- an animated screen's gameplay reel (kit ui reel) travels with it, beside the gauges (not a screen)
					local reelSrc = `{Config.path("ui")}/{name}.reel.json`
					if fs.isFile(reelSrc) then
						local starterRoot = Library.starter(if root == "" then nil else root)
						Config.ensureDir(`{starterRoot}/ui/reels`)
						fs.writeFile(`{starterRoot}/ui/reels/{name}.reel.json`, fs.readFile(reelSrc))
					end
					-- the PROCESS page (kit/ui/exemplar.py, frozen here with its rounds): `kit new screen --from` copies
					-- HOW it was made — the stills, the pieces by route with their recipes, the owner's words
					local starterRoot = Library.starter(if root == "" then nil else root)
					Config.ensureDir(`{starterRoot}/ui/process`)
					Run.content("promote process page", Run.tool("python"), {
						"kit/ui/exemplar.py",
						name,
						"--specs",
						Config.path("ui"),
						"--out",
						`{starterRoot}/ui/process/{name}.md`,
					})
				end
			end
			local promoteNextAction = if home ~= ""
				then `commit the kit home; start from it anywhere: lune run kit new {kind} <name> --from {name}`
				elseif
					fs.isFile("kit/UPSTREAM.json")
				then `commit kit/starter locally; to share upstream open a pull request at https://github.com/mayusi/parallax — start from it: lune run kit new {kind} <name> --from {name}`
				else `commit kit/starter; start from it anywhere: lune run kit new {kind} <name> --from {name}`
			if starterRecordProblem then
				-- (a new project would hold the promoted effect to the making gates, and the home's specs go red)
				return Run.report(
					"promote",
					{},
					C.TOOLCHAIN,
					`promote: {kind} {name} is an example, but {starterRecordProblem}`,
					"python kit/vfx/starters.py --write   (in the kit's home), then " .. promoteNextAction
				)
			end
			return Run.report(
				"promote",
				{},
				C.PASS,
				`promote: {kind} {name} is now an example{if home ~= "" then " in the kit home (" .. home .. ")" else ""}`,
				promoteNextAction
			)
		end
	)

	Cli.command(
		"kit",
		"sync",
		"sync [--force]",
		"pull the latest kit, lessons and examples from the kit's home into this project",
		function(rawArgs)
			local _, flags = Cli.parse(rawArgs)
			local home = Learn.home()
			if home == "" then
				-- no kit home to update from: what put the kit's files here (kit/lib/origin.luau) - a GitHub release is
				-- `upgrade`'s; a kit from a clone whose kit/HOME is gone or points nowhere is updated from a clone
				local origin = Origin.of()
				if origin == "release" then
					return Run.report(
						"sync",
						{},
						C.PASS,
						"sync: this project was installed from a GitHub release; use `upgrade` to get the latest kit",
						"lune run parallax upgrade"
					)
				end
				if origin == "clone" then
					-- (`upgrade` needs the record: a 3.0.0 kit keeps none, and is updated from a clone once first)
					return Run.report(
						"sync",
						{},
						C.USAGE,
						`sync: {Learn.homeProblem() or "kit/HOME is gone"} — this project's kit came from a clone of the kit`,
						"in a clone of the kit: lune run parallax update <this project>"
							.. (
								if Origin.record()
									then "   (or here: lune run parallax upgrade, for the GitHub release)"
									else ""
							)
					)
				end
				return Run.report(
					"sync",
					{},
					C.USAGE,
					"sync: this project is the kit's home (or kit/HOME points nowhere)",
					"from the home: lune run kit update <project>"
				)
			end
			local updateArgs = { "run", "kit", "update", process.cwd }
			if flags.force then
				table.insert(updateArgs, "--force")
			end
			local ok, r = pcall(process.exec, Run.tool("lune"), updateArgs, { cwd = home })
			if not ok or not r.ok then
				-- the update's own LAST summary / next_action say why (init prints its own report before it): a
				-- refusal - this project holds a later kit than the home's - is a usage answer, not a crash
				local why, todo
				if ok then
					for line in string.gmatch(r.stdout, "summary:%s*([^\r\n]+)") do
						why = line
					end
					for line in string.gmatch(r.stdout, "next_action:%s*([^\r\n]+)") do
						todo = line
					end
				end
				local refused = ok and r.code == C.USAGE
				return Run.report(
					"sync",
					{},
					if refused then C.USAGE else C.TOOLCHAIN,
					`sync: update from the home ({home}) failed{if why then " — " .. why else ""}`,
					if refused and todo
						then todo
						else `cd {home}; lune run kit update {process.cwd}   ({if ok then r.stderr else tostring(r)})`
				)
			end
			return Run.report("sync", {}, C.PASS, `sync: kit refreshed from {home}`, "lune run kit verify")
		end
	)
end

return Learn

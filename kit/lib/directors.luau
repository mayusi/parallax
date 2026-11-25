--!strict
-- directors.luau — what re-learns BY ITSELF when the owner's record changes (2026-11-08, sprint 3: "the distil and the
-- directors update themselves"). The VFX and UI creative-director profiles (kit/vfx/director.py learn, kit/ui/direct.py
-- learn) are plain distillations of the record - no model - so they re-run after every verdict, lesson and rule edit
-- of their lane whose inputs changed, instead of waiting for someone to remember. A lane's checks
-- (kit/checks/checks.py) are re-tested against the owner's verdicts after each verdict (quick: no GPU measure).
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Run = require("./run")
local Vault = require("./vault")

local Directors = {}

-- each director's learn command and what it reads beyond the lane's golden / graveyard / orders / rules / lessons -
-- the same paths its Python reads (a file left out here is one whose change would not re-learn the profile)
export type Learn = { argv: { string }, inputs: { string } }
Directors.LEARN = {
	vfx = {
		argv = { "kit/vfx/director.py", "learn" },
		-- the taste rules, and the verdicts its calibration reads (loved = golden + verdicts 7+ + praise in words)
		inputs = { "kit/knowledge/vault/vfx/director_rules.json", "kit/knowledge/vault/vfx/verdicts/*.md" },
	},
	ui = {
		argv = { "kit/ui/direct.py", "learn" },
		-- the shared orders, the owner's words lexicon, every direction brief (the owner's picks and feedback)
		inputs = {
			"kit/knowledge/vault/shared/orders.md",
			"kit/ui/direct_lexicon.json",
			"assets/ui/directions/*.json",
			"games/*/assets/ui/directions/*.json",
		},
	},
} :: { [string]: Learn }

-- a path whose segments may hold "*" ("games/*/assets/ui/directions/*.json") -> the files it names, sorted
function Directors.expand(pattern: string): { string }
	local segs = string.split(pattern, "/")
	local out: { string } = {}
	local function walk(prefix: string, i: number)
		if i > #segs then
			if fs.isFile(prefix) then
				table.insert(out, prefix)
			end
			return
		end
		local seg = segs[i]
		if not string.find(seg, "*", 1, true) then
			walk(if prefix == "" then seg else `{prefix}/{seg}`, i + 1)
			return
		end
		local dir = if prefix == "" then "." else prefix
		if not fs.isDir(dir) then
			return
		end
		local escaped = string.gsub(seg, "[%^%$%(%)%%%.%[%]%+%-%?]", "%%%0")
		local pat = "^" .. string.gsub(escaped, "%*", ".*") .. "$"
		local names = fs.readDir(dir)
		table.sort(names)
		for _, n in names do
			if string.match(n, pat) then
				walk(if prefix == "" then n else `{prefix}/{n}`, i + 1)
			end
		end
	end
	walk("", 1)
	return out
end

-- what a profile is distilled from, as one digest: each input's name and the digest of its whole text (one changed
-- byte anywhere changes it; a git checkout that rewrites a file with the same content does not - file times would).
-- `dept` adds that director's own inputs (Directors.LEARN)
function Directors.fingerprint(vaultDir: string, dept: string?): string
	local parts = {}
	local function add(path: string, label: string)
		if fs.isFile(path) then
			table.insert(parts, `{label}:{Vault.digest(fs.readFile(path))}`)
		end
	end
	for _, f in { "golden.md", "graveyard.md", "orders.md", "rules.md" } do
		add(`{vaultDir}/{f}`, f)
	end
	local lessons = `{vaultDir}/lessons`
	if fs.isDir(lessons) then
		local names = fs.readDir(lessons)
		table.sort(names)
		for _, f in names do
			add(`{lessons}/{f}`, f)
		end
	end
	local learn = if dept then Directors.LEARN[dept] else nil
	for _, pattern in (if learn then learn.inputs else {}) :: { string } do
		for _, path in Directors.expand(pattern) do
			add(path, path)
		end
	end
	return Vault.digest(table.concat(parts, "|"))
end

local function stampPath(dept: string): string
	return `.verify/director-{dept}.json`
end

-- has what the profile is distilled from changed since it last re-learned? (the profile carries its own time stamp,
-- so re-learning when nothing changed would still rewrite it: a churn line in git after every verdict)
function Directors.stale(dept: string, vaultDir: string): boolean
	local path = stampPath(dept)
	if not fs.isFile(path) or not fs.isFile(`{vaultDir}/director.md`) then
		return true
	end
	local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return not (ok and type(j) == "table" and j.fingerprint == Directors.fingerprint(vaultDir, dept))
end

-- one line saying what happened (nil when the lane has no director, or its profile is already up to date)
function Directors.relearn(dept: string?, vaultDir: string?): string?
	local learn = if dept then Directors.LEARN[dept] else nil
	if not learn then
		return nil
	end
	if vaultDir and not Directors.stale(dept :: string, vaultDir) then
		return nil
	end
	local step = Run.spawn(`{dept} director learn`, Run.tool("python"), learn.argv, true)
	if step.ok then
		if vaultDir then
			if not fs.isDir(".verify") then
				fs.writeDir(".verify")
			end
			fs.writeFile(
				stampPath(dept :: string),
				serde.encode("json", { fingerprint = Directors.fingerprint(vaultDir, dept) }, true)
			)
		end
		return `the {dept} creative-director profile re-learned from the record (no one has to run learn)`
	end
	return `the {dept} director profile could not re-learn: {string.sub(string.gsub(step.tail or "", "%s+", " "), -160)}`
end

-- re-test the lane's taste model on the owner's newest scores (kit/vision/taste.py, leave-one-out; 2026-11-08,
-- sprint 5): a line only when its record changed - it switches itself on once the lane has enough that agree
function Directors.retaste(dept: string?): string?
	if not dept or not fs.isFile("build/look/index.json") then
		return nil
	end
	local step =
		Run.spawn(`{dept} taste train`, Run.tool("python"), { "kit/vision/run.py", "taste", "train", dept }, true)
	local r = step.result or {}
	if not step.ok or r.written ~= true then
		return nil
	end
	return `the {dept} {tostring(r.line or r.summary)}`
end

-- re-test the lane's checks against the owner's verdicts (nil when the lane keeps none)
function Directors.retest(dept: string?, vaultDir: string?): string?
	if not dept or not vaultDir or not fs.isFile(`{vaultDir}/checks.json`) then
		return nil
	end
	local step = Run.spawn(
		`{dept} checks validate`,
		Run.tool("python"),
		{ "kit/checks/checks.py", "validate", dept, "--quick" },
		true
	)
	local r = step.result or {}
	if not step.ok then
		return `the {dept} checks could not re-test: {r.error or string.sub(step.tail or "", -120)}`
	end
	local parts = {}
	for status, n in (if type(r.status) == "table" then r.status else {}) do
		table.insert(parts, `{n} {status}`)
	end
	table.sort(parts)
	return `the {dept} checks re-tested against the owner's verdicts: {if #parts > 0
		then table.concat(parts, ", ")
		else "none"} (kit checks validate {dept} for the detail)`
end

return Directors

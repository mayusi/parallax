--!strict
-- playtests.luau — playtest results reach the vault (2026-11-08, sprint 4: proposal 13 - they stayed in build/,
-- ignored by git, and the QA lane's record never saw one). Every `kit playtest run` / `record` updates ONE note per
-- playtest, kit/knowledge/vault/qa/playtests/<name>.md: its status now, what failed, and its last runs (newest first)
-- - a note per run would bury the vault. kit start qa lists the ones failing now.
local fs = require("@lune/fs")

local Vault = require("./vault")

local Playtests = {}

Playtests.KEEP = 10 -- runs kept in a note

function Playtests.dir(): string
	return Vault.dir("qa") .. "/playtests"
end

local function fileOf(name: string): string
	return `{Playtests.dir()}/{Vault.slug(name)}.md`
end

-- the run as one line: date, status, checks passed, and the performance probe when it measured one
local function runLine(date: string, passed: boolean, ok: number, total: number, perf: any): string
	local p = if type(perf) == "table" and perf.memoryMb
		then ` · {perf.memoryMb} MB · {perf.frameMs or "?"} ms/frame`
		else ""
	return `  - {date} {if passed then "pass" else "FAIL"} {ok}/{total}{p}`
end

-- one run of a playtest into its note -> the note's path
function Playtests.record(
	name: string,
	passed: boolean,
	ok: number,
	total: number,
	failed: { string },
	perf: any?
): string
	local path = fileOf(name)
	local runs = {}
	if fs.isFile(path) then
		for line in string.gmatch(string.gsub(fs.readFile(path), "\r\n", "\n"), "[^\n]+") do
			if string.match(line, "^  %- %d%d%d%d%-%d%d%-%d%d ") then
				table.insert(runs, line)
			end
		end
	end
	local today = Vault.today()
	table.insert(runs, 1, runLine(today, passed, ok, total, perf))
	while #runs > Playtests.KEEP do
		table.remove(runs)
	end
	local lines = {
		"---",
		"kind: playtest",
		"area: qa",
		`name: {name}`,
		`status: {if passed then "pass" else "fail"}`,
		`date: {today}`,
		'links: ["[[qa/index]]"]',
		"---",
		"",
		`# Playtest {name}: {if passed then "pass" else "FAIL"} ({ok}/{total} checks, {today})`,
		"",
	}
	if #failed > 0 then
		table.insert(lines, "- What failed in the last run:")
		for i = 1, math.min(5, #failed) do
			table.insert(lines, `  - {string.sub(string.gsub(failed[i], "%s+", " "), 1, 200)}`)
		end
	end
	table.insert(lines, `- Runs (newest first; kit playtest run {name}):`)
	for _, r in runs do
		table.insert(lines, r)
	end
	if not fs.isDir(Playtests.dir()) then
		fs.writeDir(Playtests.dir())
	end
	fs.writeFile(path, table.concat(lines, "\n") .. "\n")
	return path
end

-- the playtests failing now -> { "name (date): what failed first" }
function Playtests.failing(): { string }
	local out = {}
	for _, n in Vault.notes("qa", "playtests") do
		if n.front.status == "fail" then
			local first = string.match(n.body, "What failed in the last run:\n%s*%- ([^\n]+)") or "see the note"
			table.insert(out, `{n.front.name or "?"} ({n.front.date or "?"}): {first}`)
		end
	end
	table.sort(out)
	return out
end

return Playtests

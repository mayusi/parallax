-- moderation.luau (kit) — the MODERATION GATE: nothing that Roblox moderation could flag leaves this PC.
-- Roblox moderates the ACCOUNT that uploads blood or gore: Open Cloud then answers 403 'User is moderated' to every
-- call, and sound takes titled *flesh* are held the same way. An uploaded asset is judged on its own - a game's age
-- label does not cover it. Standing order: no blood, no gore, nothing moderation could flag,
-- ever; when in doubt, leave it out.
-- Two halves, run on every file `kit upload` would send (and by `kit moderation check`):
--   WORDS  - the file's name and its upload title, split into words (camelCase, _, -, digits): a banned word holds it
--   IMAGES - every PNG measured by kit/tools/mod_gate.py: blood's colour over most of what it shows, or a splatter
-- A held file is never sent. It is changed, or cleared BY NAME AND CONTENT (its hash) by the owner - or the
-- governor, whom the owner told to judge uploads - in their words: `kit moderation clear <file> "<words>" --by owner`.
-- A cleared file that changes is held again.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Config = require("./config")
local Integrity = require("./integrity")
local Run = require("./run")
local UploadJobs = require("./uploadjobs")

local Moderation = {}

-- words that hold a file outright (a whole word of its name or title)
local WORDS = {
	-- blood and gore (Roblox moderates the uploading account)
	"blood",
	"bloody",
	"bloodied",
	"bleed",
	"bleeding",
	"gore",
	"gory",
	"gorey",
	"flesh",
	"fleshy",
	"guts",
	"gut",
	"corpse",
	"corpses",
	"cadaver",
	"carcass",
	"wound",
	"wounds",
	"wounded",
	"stab",
	"stabbed",
	"stabbing",
	"entrails",
	"viscera",
	"severed",
	"splatter",
	-- adult
	"nude",
	"nudity",
	"naked",
	"nsfw",
	"hentai",
	"sex",
	"sexy",
	"lewd",
	"fetish",
	-- drugs
	"cocaine",
	"heroin",
	"meth",
	"marijuana",
	"cannabis",
	"drug",
	"drugs",
	-- hate
	"nazi",
	"swastika",
	"kkk",
	"hitler",
	-- self-harm
	"suicide",
	"selfharm",
	"noose",
}
-- word starts that hold a file (one word may run several together: "bloodsplat", "decapitated")
local STEMS = {
	"blood",
	"decapitat",
	"dismember",
	"mutilat",
	"disembowel",
	"eviscerat",
	"intestin",
	"porn",
	"narcotic",
	"fuck",
	"shit",
	"bitch",
	"cunt",
	"retard",
}

local banned: { [string]: boolean } = {}
for _, w in WORDS do
	banned[w] = true
end

-- "BloodPool_02-splat" -> { "blood", "pool", "splat" }
function Moderation.words(text: string): { string }
	local spaced = string.gsub(text, "(%l)(%u)", "%1 %2")
	spaced = string.gsub(spaced, "(%u)(%u%l)", "%1 %2")
	local out = {}
	for w in string.gmatch(string.lower(spaced), "%a+") do
		table.insert(out, w)
	end
	return out
end

-- the banned words in a text -> { "blood", ... } (empty when clean)
function Moderation.terms(text: string): { string }
	local hits, seen = {}, {}
	for _, w in Moderation.words(text) do
		local hit = if banned[w] then w else nil
		if not hit then
			for _, s in STEMS do
				if string.sub(w, 1, #s) == s then
					hit = w
					break
				end
			end
		end
		if hit and not seen[hit] then
			seen[hit] = true
			table.insert(hits, hit)
		end
	end
	return hits
end

local function clearedPath(): string
	return Config.root() .. "board/moderation_cleared.json"
end

function Moderation.cleared(): { [string]: any }
	local p = clearedPath()
	if not fs.isFile(p) then
		return {}
	end
	local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(p))
	return if ok and type(data) == "table" then data else {}
end

-- record a clearing: the file's CONTENT is cleared (a changed file is held again)
function Moderation.clear(file: string, words: string, by: string, at: string): (boolean, string)
	if not fs.isFile(file) then
		return false, `{file}: no such file`
	end
	if by ~= "owner" and by ~= "governor" then
		return false, `--by {by}: only the owner, or the governor he named, clears a held file`
	end
	if #(string.gsub(words, "%s", "")) < 3 then
		return false, "the clearing needs their words"
	end
	local all = Moderation.cleared()
	local hash = Integrity.hash(fs.readFile(file))
	all[hash] = { file = file, by = by, words = words, at = at }
	Config.ensureDir(Config.root() .. "board")
	fs.writeFile(clearedPath(), serde.encode("json", all, true) .. "\n")
	return true, hash
end

export type Verdict = {
	file: string,
	title: string,
	held: boolean,
	why: { string },
	crimson: number?,
	cleared: string?, -- whose words cleared it
}

-- measure every image with kit/tools/mod_gate.py (one python for all) -> { [file]: result }; nil + why when it fails
local function images(files: { string }): ({ [string]: any }?, string?)
	if #files == 0 then
		return {}, nil
	end
	local args = { "-I", "kit/tools/mod_gate.py" }
	for _, f in files do
		table.insert(args, f)
	end
	local ok, res = pcall(process.exec, Run.tool("python"), args)
	if not ok then
		return nil, `the image check could not run: {res}`
	end
	local line = nil
	for l in string.gmatch(res.stdout, "[^\r\n]+") do
		if string.sub(l, 1, 1) == "{" then
			line = l
		end
	end
	local okJ, data = pcall(serde.decode, "json" :: any, line or "")
	if not okJ or type(data) ~= "table" then
		return nil, `the image check gave no verdict: {string.sub(res.stderr, -300)}`
	end
	if data.unreadable and #data.unreadable > 0 then
		return nil, `the image check could not read {data.unreadable[1].file}: {data.unreadable[1].error}`
	end
	local out = {}
	for _, r in data.images do
		out[r.file] = r
	end
	return out, nil
end

-- screen files before they leave: { {file, title} } -> verdicts (one per file), or nil + why when the check itself
-- failed (then NOTHING is sent: a gate that could not look is a closed gate)
function Moderation.screen(items: { { file: string, title: string } }): ({ Verdict }?, string?)
	local pngs = {}
	for _, it in items do
		if string.lower(string.sub(it.file, -4)) == ".png" then
			table.insert(pngs, it.file)
		end
	end
	local measured, err = images(pngs)
	if not measured then
		return nil, err
	end
	local cleared = Moderation.cleared()
	local out: { Verdict } = {}
	for _, it in items do
		local why = {}
		local name = string.match(it.file, "([^/\\]+)$") or it.file
		for _, t in Moderation.terms(name .. " " .. it.title) do
			table.insert(why, `the word "{t}"`)
		end
		local m = measured[it.file]
		if m and m.flagged then
			table.insert(why, m.why)
		end
		local v: Verdict = {
			file = it.file,
			title = it.title,
			held = #why > 0,
			why = why,
			crimson = if m then m.crimson else nil,
		}
		if v.held and fs.isFile(it.file) then
			local c = cleared[Integrity.hash(fs.readFile(it.file))]
			if c then
				v.held = false
				v.cleared = `{c.by}: "{c.words}" ({c.at})`
			end
		end
		table.insert(out, v)
	end
	return out, nil
end

-- what `kit upload` would send next (kit/lib/uploadjobs.luau: the upload's own list - private studies and held art
-- are never sent and are not screened; every file new or changed since the upload ledger saw it), as screening items:
-- the audit screens these, so a held file shows up before anyone uploads. The animations as last exported (the audit
-- never loads the place).
function Moderation.pending(): { { file: string, title: string } }
	local ledgerPath = Config.path("uploads")
	local ledger = {}
	if ledgerPath and fs.isFile(ledgerPath) then
		local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(ledgerPath))
		ledger = if ok and type(data) == "table" then data else {}
	end
	local out = {}
	for _, job in UploadJobs.jobs(Config.load().name or "game", true) do
		if fs.isFile(job.file) then
			local entry = ledger[job.file]
			if not entry or entry.hash ~= Integrity.hash(fs.readFile(job.file)) then
				table.insert(out, { file = job.file, title = job.name })
			end
		end
	end
	return out
end

-- the log written before anything is sent: every file screened, held or not, and why
function Moderation.log(verdicts: { Verdict }, at: string): string
	local p = Config.build("moderation.json")
	Config.ensureDir((string.match(p, "^(.*)/[^/]*$") or "."))
	fs.writeFile(p, serde.encode("json", { at = at, files = verdicts }, true) .. "\n")
	return p
end

return Moderation

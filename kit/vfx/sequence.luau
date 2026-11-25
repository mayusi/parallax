--!nocheck
-- sequence.luau — a V5 sequence file checked and compiled by THE rules the game plays it with
-- (src/kit/VfxSequenceRules.luau), for kit/vfx/sequence.py: one source of truth, never a Python copy of the rules.
--   lune run kit/vfx/sequence.luau <file.seq.json>
-- prints one JSON line { ok, problems, impact, frames, events: [{ frame, kind, beat, ends }] } (events only when ok)
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Rules = require("../../src/kit/VfxSequenceRules")

local path = process.args[1]
local okRead, raw = pcall(fs.readFile, path or "")
if not okRead then
	print(serde.encode("json", { ok = false, problems = { `no sequence file at {tostring(path)}` } }))
	process.exit(1)
end
local okJson, seq = pcall(serde.decode, "json", raw)
if not okJson then
	print(serde.encode("json", { ok = false, problems = { `{path} is not JSON: {tostring(seq)}` } }))
	process.exit(1)
end
local ok, problems = Rules.validate(seq)
local result: any = { ok = ok, problems = problems }
if ok then
	local tl = Rules.compile(seq)
	local events = {}
	for _, ev in tl.events do
		table.insert(events, { frame = ev.frame, kind = ev.kind, beat = ev.beat, ends = ev.ends })
	end
	result.events = events
	result.frames = tl.frames
	result.impact = Rules.impactBeat(seq)
	result.kind = seq.kind or "plain"
end
print(serde.encode("json", result))
process.exit(if ok then 0 else 1)

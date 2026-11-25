-- clip_of.luau — `lune run kit/anim/clip_of.luau <spec.json | clip.json> <out.clip.json> [R6]`: one spec -> its
-- neutral clip (and, with R6, the folded R6 clip), nothing else. Given a CLIP (a gait's or a bake's output: it has
-- `times` and `joints[...].frames`) it only folds. The Python tests use it to check kit/anim/clip.py's sampler
-- against the kit's own (kit/lib/anim.luau) — two implementations of the spec's semantics must agree — and to run
-- the R6 fold (Anim.foldToR6) on generated gaits exactly as `kit anim` does.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Anim = require("../lib/anim")

local inPath, outPath, rig = process.args[1], process.args[2], process.args[3]
if not inPath or not outPath then
	print("usage: lune run kit/anim/clip_of.luau <spec.json | clip.json> <out.clip.json> [R6]")
	process.exit(7)
end
local data = serde.decode("json", fs.readFile(inPath))
local clip, issues
if type(data.times) == "table" and type(data.joints) == "table" then
	clip, issues = data, {} -- already a clip: fold it as kit anim would
else
	clip, issues = Anim.clipFromSpec(data, { source = { kind = "spec", file = inPath } })
end
for _, i in issues do
	print(`[{i.severity}] {i.path}: {i.message}`)
end
if not clip then
	process.exit(6)
end
if rig == "R6" then
	clip = (Anim.foldToR6(clip))
end
fs.writeFile(outPath, serde.encode("json", clip, true))
print(`clip {clip.name} ({clip.rig}): {#clip.times} frames -> {outPath}`)

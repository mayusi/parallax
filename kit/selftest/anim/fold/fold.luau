-- fold.luau — an R15 clip through the kit's own fold (kit/lib/anim.luau Anim.foldToR6), for the fixtures beside it:
--   lune run kit/selftest/anim/fold/fold.luau <R15 clip.json> <out R6 clip.json>
-- (kit/test/python/test_anim_fold_loss.py reads the pairs; made once, 2026-11-15, from that test's own `source()`)
local Anim = require("../../../lib/anim")
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local clip = serde.decode("json", fs.readFile(process.args[1]))
local folded = Anim.foldToR6(clip)
fs.writeFile(process.args[2], serde.encode("json", folded))

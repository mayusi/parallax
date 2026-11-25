-- chartplan.luau (kit) — a beat chart's PLAN as one comparable line: the duration, then each beat's t, len, hold and
-- key. It is the text kit/vfx/chart.py plan_key() writes into the chart's "approved" when the owner says yes, and the
-- ONE Luau reading of it: the scene gate (kit/cmd/content.luau) and the review page (kit/lib/review.luau) both call
-- this, so they cannot disagree with each other (a review, 2026-11-12: each had its own copy). It reads the JSON the
-- way Python does where the two languages differ: a beat's "key" by Python's idea of true (kit/lib/pytruth.luau),
-- and "beats" only when it is a LIST (Python iterating an object sees its key names and skips them).
local truthy = require("./pytruth")

return function(chart: any): string
	local parts = {}
	local beats = if type(chart.beats) == "table" and #chart.beats > 0 then chart.beats else {}
	for _, b in beats do
		if type(b) == "table" then
			table.insert(
				parts,
				string.format(
					"%.2f,%.2f,%.2f,%d",
					tonumber(b.t) or 0,
					tonumber(b.len) or 0,
					tonumber(b.hold) or 0,
					if truthy(b.key) then 1 else 0
				)
			)
		end
	end
	return string.format("%.2f|", tonumber(chart.duration) or 0) .. table.concat(parts, ";")
end

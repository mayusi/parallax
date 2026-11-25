-- pytruth.luau (kit) — what PYTHON calls true, for the places where Luau and a Python tool must read one JSON value
-- the same way. Luau calls 0 and "" true; Python does not. A beat chart's plan text is written by kit/vfx/chart.py
-- (`1 if b.get("key") else 0`) and compared by the scene gate and the review page in Luau: a hand-edited "key": 0
-- read as the key beat on one side only, and the chart read "changed" right after every approval (a review,
-- 2026-11-12).
return function(v: any): boolean
	if type(v) == "number" then
		return v ~= 0
	elseif type(v) == "string" then
		return v ~= ""
	elseif type(v) == "table" then
		return next(v) ~= nil
	end
	return v == true
end

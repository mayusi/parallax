--!strict
-- regressions.luau — the regression corpus's cases (tests/regressions.json: `kit bug` writes it, `kit mutate
-- --regressions` replants every case, `kit accept` counts them; 2026-11-08, sprint 4). The same planted change is never
-- filed twice, and two different bugs never share an id (an id is the bug's words, cut to 48 characters).
local Regressions = {}

export type Case = { id: any, module: any, line: any, from: any, to: any }

-- the same planted change: the same module, line, from and to
function Regressions.same(a: Case, b: Case): boolean
	return a.module == b.module and a.line == b.line and a.from == b.from and a.to == b.to
end

-- where a new case goes -> (its id, the case already filed when it is the same change)
function Regressions.place(cases: { Case }, case: Case, base: string): (string, Case?)
	for _, c in cases do
		if Regressions.same(c, case) then
			return tostring(c.id), c
		end
	end
	local taken: { [string]: boolean } = {}
	for _, c in cases do
		taken[tostring(c.id)] = true
	end
	local id, n = base, 1
	while taken[id] do
		n += 1
		id = `{base}-{n}`
	end
	return id, nil
end

return Regressions

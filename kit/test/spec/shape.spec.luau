-- shape.spec.luau — the size / shape guards (kit/qa/shape.luau): long functions and services, require cycles; blocks
-- counted right (elseif, repeat ... until, a field named end, keywords in strings and comments never count).
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")

local Shape = require("../../qa/shape")

local FIX = "build/_shapefix"

local function put(rel: string, text: string)
	local path = FIX .. "/" .. rel
	local cur = ""
	local parts = string.split(path, "/")
	for i = 1, #parts - 1 do
		cur = if cur == "" then parts[i] else cur .. "/" .. parts[i]
		if not fs.isDir(cur) then
			fs.writeDir(cur)
		end
	end
	fs.writeFile(path, text)
end

local function body(n: number): string
	local lines = {}
	for i = 1, n do
		table.insert(lines, `\tlocal v{i} = {i}`)
	end
	return table.concat(lines, "\n")
end

local function kinds(findings: { Shape.Finding }, kind: string): number
	local n = 0
	for _, f in findings do
		if f.kind == kind then
			n += 1
		end
	end
	return n
end

return function()
	test.suite("kit shape guards", function()
		test.case("functions are found with their real ends", function()
			local src = table.concat({
				"local function a(x)", -- 1
				"\tif x then", -- 2
				"\t\treturn 1", -- 3
				"\telseif x == 2 then", -- 4
				"\t\treturn 2", -- 5
				"\tend", -- 6
				"\trepeat x -= 1 until x < 0", -- 7
				'\tlocal s = "function end then do"', -- 8
				"\t-- function do end", -- 9
				"\tlocal t = { finish = 1 }; local e = t.end_ or t", -- 10
				"\tfor i = 1, 3 do print(i) end", -- 11
				"end", -- 12
				"local b = function() return 1 end", -- 13
			}, "\n")
			local fns = Shape.functions(src)
			check.equal(#fns, 2)
			check.equal(fns[1].first, 1)
			check.equal(fns[1].last, 12)
			check.equal(fns[1].name, "a")
			check.equal(fns[2].first, 13)
			check.equal(fns[2].last, 13)
		end)
		test.case("a long function, a long service and a require cycle are each one warning", function()
			if fs.isDir(FIX) then
				fs.removeDir(FIX)
			end
			put("src/shared/Long.luau", "local M = {}\nfunction M.big()\n" .. body(90) .. "\nend\nreturn M\n")
			put("src/shared/Short.luau", "local M = {}\nfunction M.small()\n" .. body(10) .. "\nend\nreturn M\n")
			put("src/server/HugeService.server.luau", body(650) .. "\n")
			put("src/shared/A.luau", 'local B = require(script.Parent:WaitForChild("B"))\nreturn {}\n')
			put("src/shared/B.luau", "local A = require(script.Parent.A)\nreturn {}\n")
			put("src/kit/Giant.luau", "local function g()\n" .. body(200) .. "\nend\n") -- (the kit's own copy: skipped)
			local f = Shape.scanDir(FIX .. "/src")
			check.equal(kinds(f, "function"), 1)
			check.equal(kinds(f, "service"), 1)
			check.equal(kinds(f, "cycle"), 1)
			fs.removeDir(FIX)
		end)
		test.case("requires name the module, from a WaitForChild string or a dotted path", function()
			local r = Shape.requires(
				'local X = require(game.ReplicatedStorage.Shared:WaitForChild("XRules"))\nlocal Y = require(script.Parent.YConfig)\n-- require(Nope)'
			)
			check.equal(#r, 2)
			check.equal(r[1], "XRules")
			check.equal(r[2], "YConfig")
		end)
	end)
end

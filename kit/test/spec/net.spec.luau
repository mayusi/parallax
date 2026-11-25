-- net.spec.luau — network schemas -> generated remotes (kit/lib/net): validation of the schema, and the generated
-- code rate-limits + Guard-checks every client argument (proven by the kit's own security audit on the output).
local frk = require("../frk")
local test, check = frk.test, frk.check

local Audit = require("../../lib/audit")
local Net = require("../../lib/net")

local GOOD = {
	system = "Strike",
	remotes = {
		Request = {
			dir = "toServer",
			rate = { 5, 2 },
			args = {
				{ name = "target", type = "vector3", max = 500 },
				{ name = "power", type = "number", min = 0, max = 1 },
				{ name = "mode", type = "enum", values = { "light", "heavy" } },
			},
		},
		Reply = {
			dir = "toClient",
			args = { { name = "ok", type = "boolean" }, { name = "reason", type = "string", max = 64 } },
		},
		Ping = { dir = "toServer", rate = { 2, 1 } },
	},
}

return function()
	test.suite("Net.validate", function()
		test.case("a good schema has no issues", function()
			check.equal(#Net.validate(GOOD), 0)
		end)
		test.case("client numbers need a range, strings a length, vectors a magnitude, requests a rate", function()
			local issues = Net.validate({
				system = "Bad",
				remotes = {
					Ask = {
						dir = "toServer",
						args = {
							{ name = "n", type = "number" },
							{ name = "s", type = "string" },
							{ name = "aim", type = "vector3" },
							{ name = "n", type = "boolean" },
							{ name = "x", type = "table" },
						},
					},
				},
			})
			local text = ""
			for _, i in issues do
				text ..= i.message .. "\n"
			end
			check.is_true(string.find(text, "rate", 1, true) ~= nil)
			check.is_true(string.find(text, '"min" and "max"', 1, true) ~= nil)
			check.is_true(string.find(text, '"max" length', 1, true) ~= nil)
			check.is_true(string.find(text, "magnitude", 1, true) ~= nil)
			check.is_true(string.find(text, "duplicate", 1, true) ~= nil)
			check.is_true(string.find(text, "type must be", 1, true) ~= nil)
		end)
	end)

	test.suite("Net.compile", function()
		test.case("every client argument is Guard-checked before the handler, behind a rate limit", function()
			local src = Net.compile(GOOD, "assets/net/Strike.net.json")
			check.not_nil(src)
			local s = src :: string
			check.is_true(string.find(s, "Guard.vector3(a1)", 1, true) ~= nil)
			check.is_true(string.find(s, "Magnitude > 500", 1, true) ~= nil)
			check.is_true(string.find(s, "Guard.number(a2, 0, 1)", 1, true) ~= nil)
			check.is_true(string.find(s, 'Guard.oneOf(a3, { "light", "heavy" })', 1, true) ~= nil)
			check.is_true(string.find(s, "limit:take(player.UserId, os.clock())", 1, true) ~= nil)
			check.is_true(string.find(s, "handler(player, v1, v2, v3)", 1, true) ~= nil)
		end)
		test.case("the flight recorder hears every server call: limited, rejected per argument, ok", function()
			local s = Net.compile(GOOD) :: string
			check.is_true(string.find(s, 'require(Kit:WaitForChild("Recorder"))', 1, true) ~= nil)
			check.is_true(string.find(s, 'Recorder.record("Strike.Request", player.UserId, "limited")', 1, true) ~= nil)
			for _, arg in { "target", "power", "mode" } do
				local line = `Recorder.record("Strike.Request", player.UserId, "rejected {arg}", a1, a2, a3)`
				check.is_true(string.find(s, line, 1, true) ~= nil)
			end
			-- (the vector's magnitude check rejects too, recorded the same way)
			local _, n = string.gsub(s, 'Recorder.record%("Strike.Request", player.UserId, "rejected target"', "")
			check.equal(n, 2)
			local ok = string.find(s, 'Recorder.record("Strike.Request", player.UserId, "ok", a1, a2, a3)', 1, true)
			local handler = string.find(s, "handler(player, v1, v2, v3)", 1, true)
			check.is_true(ok ~= nil and handler ~= nil and (ok :: number) < (handler :: number))
			check.is_true(string.find(s, 'Recorder.record("Strike.Ping", player.UserId, "ok")', 1, true) ~= nil)
		end)
		test.case("the kit's own security audit passes the generated server code", function()
			local src = Net.compile(GOOD) :: string
			local findings = Audit.scan("src/net/StrikeNet.luau", src, true)
			local errors = 0
			for _, f in findings do
				if f.severity == "error" or f.rule == "no-rate-limit" then
					errors += 1
				end
			end
			check.equal(errors, 0)
		end)
		test.case(
			"keywords, generated names, non-string enums and absurd rates are refused (review 2026-10-13)",
			function()
				local cases = {
					{ system = "S", remotes = { ["end"] = { dir = "toClient", args = {} } } },
					{
						system = "S",
						remotes = { Tell = { dir = "toClient", args = { { name = "p", type = "boolean" } } } },
					},
					{
						system = "S",
						remotes = { Tell = { dir = "toClient", args = { { name = "local", type = "boolean" } } } },
					},
					{
						system = "S",
						remotes = {
							Ask = {
								dir = "toServer",
								rate = { 1, 1 },
								args = { { name = "player", type = "boolean" } },
							},
						},
					},
					{
						system = "S",
						remotes = {
							Ask = { dir = "toServer", rate = { 1, 1 }, args = { { name = "ev", type = "boolean" } } },
						},
					},
					{
						system = "S",
						remotes = {
							Ask = {
								dir = "toServer",
								rate = { 1, 1 },
								args = { { name = "m", type = "enum", values = { {}, true } } },
							},
						},
					},
					{ system = "S", remotes = { Ask = { dir = "toServer", rate = { 1e12, 1e12 } } } },
					-- re-review: "_" repeated the fireExcept loop-variable bug; toClient bounds went unchecked into Guard
					{
						system = "S",
						remotes = { Tell = { dir = "toClient", args = { { name = "_", type = "boolean" } } } },
					},
					{
						system = "S",
						remotes = { Tell = { dir = "toClient", args = { { name = "n", type = "number", min = {} } } } },
					},
					{
						system = "S",
						remotes = {
							Tell = { dir = "toClient", args = { { name = "n", type = "number", max = math.huge } } },
						},
					},
				}
				for i, schema in cases do
					local src, issues = Net.compile(schema)
					check.equal(src, nil)
					check.is_true(#issues > 0, `case {i} must be refused`)
				end
			end
		)
		test.case("a bad schema compiles to nothing", function()
			local src, issues = Net.compile({ system = "x y", remotes = {} })
			check.equal(src, nil)
			check.is_true(#issues > 0)
		end)
	end)
end

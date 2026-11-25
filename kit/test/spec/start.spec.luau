-- start.spec.luau (kit) — `kit start <dept>` loads ONE lane in any harness: for every department the boot sheet, the
-- stage shortlist and the vault page are there, the whole text fits the start budget, and every rule moved out of the
-- shared instruction file (AGENTS.md is a router) is printed for its own department.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Start = require("../../cmd/start")({ command = function() end })
local Vault = require("../../lib/vault")

-- the start budget (vault.start_budget; 3200 since the standing orders and quality locks joined the page): pinned here
-- so a kit.config.json override can never loosen this check; the kit's own default must equal it
local BUDGET = 3200
assert(
	require("../../lib/config").DEFAULTS.vault.start_budget == BUDGET,
	"the default start budget moved: update BUDGET with it"
)
-- the rules that left the shared instruction file, and the department that must print them
local MOVED = {
	ui = { "Everything the UI pipeline makes is saved", "library/ui/" },
	vfx = { "Everything the VFX pipeline makes is saved", "library/vfx/" },
	["3d"] = {
		"kit plan <name>",
		"DOSSIER",
		"pk = a.pack()",
		"kit cad check <name> --only <Part>",
		"two reviewers, one blind",
		"a.param",
	},
	anim = { "kit anim new <Name> --pose", "UpperTorso" },
	world = { "kit world check <Name>" },
	sfx = { "kit sfx listen" },
	code = { "kit new system <Pascal>", "kit fuzz", "ReplicatedStorage.kit.<Module>" },
	qa = { "kit playtest bundle" },
	kit = { "kit selftest" },
}

return function()
	test.suite("kit start: one lane, any harness", function()
		test.case("every lane has its boot sheet, stage, page; the text fits the budget", function()
			for _, dept in Start.DEPTS do
				check.truthy(fs.isFile(`kit/knowledge/vault/{dept}/boot.md`))
				local text, blocks = Start.text(dept, nil, BUDGET)
				check.truthy(blocks.boot)
				check.truthy(blocks.stage)
				-- the department's record (last verdicts / golden / graveyard) is never lost to the budget - when it has one
				-- (a fresh project's vault holds no verdicts yet)
				local full = Vault.page(dept, 1000000, true)
				local hasRecord = string.find(full, "LAST VERDICTS", 1, true) ~= nil
					or string.find(full, "GOLDEN", 1, true) ~= nil
					or string.find(full, "GRAVEYARD", 1, true) ~= nil
				check.truthy(blocks.page or not hasRecord)
				-- the boot line every harness can paste is in it
				check.truthy(string.find(text, `lune run kit start {dept}`, 1, true))
				-- ~4 characters a token, with a small margin for the clipped page's note
				check.truthy(math.ceil(#text / 4) <= BUDGET + 60)
			end
		end)
		test.case("every content lane is told its quality locks and how the owner's go-ahead is recorded", function()
			for _, dept in { "3d", "vfx", "ui", "anim", "world", "sfx" } do
				local text, blocks = Start.text(dept, nil, BUDGET)
				check.truthy(blocks.locks)
				check.truthy(string.find(text, `lune run kit approve {dept} <name>`, 1, true))
				check.truthy(string.find(text, "--by owner", 1, true))
				check.truthy(string.find(text, `kit verdict pending {dept}`, 1, true))
			end
			check.truthy(string.find(Start.text("vfx", nil, BUDGET), "--approve", 1, true)) -- the chart's own route
			local _, codeBlocks = Start.text("code", nil, BUDGET)
			check.falsy(codeBlocks.locks) -- a lane with no content pieces has no lock section
		end)
		test.case(
			"every lane's full recipe prints for any harness (kit skill), and the start page points to it",
			function()
				for _, dept in Start.DEPTS do
					local text, why = Start.skill(dept)
					check.truthy(text and #text > 200, why)
					check.falsy(text and string.find(text, "^%-%-%-")) -- the frontmatter is not part of the recipe
					check.truthy(string.find(Start.text(dept, nil, BUDGET), `lune run kit skill {dept}`, 1, true))
				end
				local _, missing = Start.skill("no-such-lane")
				check.truthy(missing)
			end
		)
		test.case("the owner's standing orders open a lane's start page, the every-lane ones included", function()
			-- (a fresh kit ships no standing orders - the owner writes them: these two are fixtures, read in place of the
			-- vault's own orders.md files, which are never written to here)
			local realOrders = Vault.orders
			Vault.orders = function(dept: string, withSource: boolean?): { string }
				if dept == "vfx" then
					return { "Show the effect beside its references before calling it done" }
				elseif dept == "shared" then
					return { "Commit after every session" }
				end
				return realOrders(dept, withSource)
			end
			local ok, err = pcall(function()
				local text, blocks = Start.text("vfx", nil, BUDGET)
				check.truthy(blocks.orders)
				local at = string.find(text, "## Standing orders", 1, true)
				check.truthy(at and at < (string.find(text, "## Boot line", 1, true) or math.huge))
				check.truthy(string.find(text, "(every lane)", 1, true))
			end)
			Vault.orders = realOrders
			if not ok then
				error(err, 0)
			end
		end)
		test.case("every rule moved out of AGENTS.md is printed for its department", function()
			for dept, needles in MOVED do
				local text = Start.text(dept, nil, BUDGET)
				for _, needle in needles do
					check.truthy(string.find(text, needle, 1, true))
				end
			end
		end)
		test.case("the shared instruction file is a short router that points every lane to kit start", function()
			local router = fs.readFile("kit/harness/AGENTS.parallax.md") -- (renamed from AGENTS.kit.md: PARALLAX spec §5.1 7)
			check.truthy(#router <= 3500) -- AGENTS.md (router + the project's own header) stays under 4 KB
			check.truthy(string.find(router, "lune run parallax start <", 1, true))
			check.truthy(string.find(router, "--prompt", 1, true)) -- (the session needs the request compiled)
			check.truthy(string.find(router, "originality rule", 1, true)) -- the rule for everything stays shared
			-- what every lane still needs from the shared file
			for _, needle in { "kit promote", "kit sync", "≥ 7 lands in the golden set", "kit help --all", "--lane" } do
				check.truthy(string.find(router, needle, 1, true))
			end
			check.falsy(string.find(router, "Everything the UI pipeline makes is saved", 1, true))
			check.falsy(string.find(router, "Everything the VFX pipeline makes is saved", 1, true))
		end)
		test.case("a lane is shown only the handoffs that clearly belong to it", function()
			local function h(summary: string, lane: string?): string
				return `# Handoff\n\n## Summary\n{summary}\n` .. (if lane then `\n## Lane\n{lane}\n` else "")
			end
			-- the lane line decides alone
			check.truthy(Start.claims(h("anything at all", "ui"), "ui"))
			check.falsy(Start.claims(h("VFX: looks like vfx", "ui"), "vfx"))
			-- an opener naming the lane; a shared systems + sound session belongs to both
			check.truthy(Start.claims(h("VFX: built the nuke"), "vfx"))
			check.truthy(Start.claims(h("Systems/sound lane round 2: dojo"), "code"))
			check.truthy(Start.claims(h("Systems/sound lane round 2: dojo"), "sfx"))
			-- "kit world cliffs" is the world lane's, never the kit lane's
			check.truthy(Start.claims(h("kit world cliffs: rivers"), "world"))
			check.falsy(Start.claims(h("kit world cliffs: rivers"), "kit"))
			check.truthy(Start.claims(h("kit foundations: vault done"), "kit"))
			-- a passing mention is not enough
			check.falsy(Start.claims(h("fixed the vault so the ui pages are short"), "ui"))
		end)
		test.case("the lane-only rules are NOT printed for the other lanes", function()
			local ui = Start.text("ui", nil, BUDGET)
			check.falsy(string.find(ui, "Everything the VFX pipeline makes is saved", 1, true))
			local anim = Start.text("anim", nil, BUDGET)
			check.falsy(string.find(anim, "Everything the UI pipeline makes is saved", 1, true))
		end)
	end)
end

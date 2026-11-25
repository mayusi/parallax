-- vaultgate.luau — the department page before a pipeline's work, enforced in ONE place.
--
-- `kit new <kind>` and `kit plan` print the department's vault page (the owner's rules, the golden set, the
-- graveyard, the last verdicts). Resumed work goes through a pipeline's own stage commands (kit ui plan, kit vfx
-- chart, kit anim new, kit world check, kit sfx sheet, kit cad, kit trace, ...) and never saw it. Cli.dispatch now
-- calls VaultGate.before(name, args) for every command: when the command belongs to a department, the page is
-- printed first, at most once per department per window (default 120 min, kit.config.json vault.reshow_minutes),
-- so a long session pays for it once, not on every call. KIT_VAULT_PAGE=always|never overrides.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("./config")
local Vault = require("./vault")

local VaultGate = {}

-- top-level command -> department (kit plan and kit new print the page themselves: not listed)
VaultGate.DEPT_OF_COMMAND = {
	ui = "ui",
	vfx = "vfx",
	anim = "anim",
	world = "world",
	sfx = "sfx",
	["audio-check"] = "sfx",
	asset = "3d",
	cad = "3d",
	dossier = "3d",
	fit = "3d",
	gen = "3d",
	judge = "3d",
	make = "3d",
	materials = "3d",
	optimize = "3d",
	pack = "3d",
	study = "3d",
	sheet = "3d",
	sharpen = "3d",
	blockout = "3d",
	refs = "3d",
	schematic = "3d",
	showcase = "3d",
	trace = "3d",
	watch = "3d",
	library = "3d",
	learn = "3d",
	game = "code",
	move = "code",
	net = "code",
	fuzz = "code",
	mutate = "code",
	playtest = "qa",
}

-- subcommands that only look things up: no page (help, lists, searches, status checks)
local LOOKUP = {
	help = true,
	["--help"] = true,
	["-h"] = true,
	list = true,
	find = true,
	catalog = true,
	["--status"] = true,
	["--check"] = true,
}

VaultGate.STAMP = ".verify/vault_seen.json"

local function now(): number
	return os.time()
end

local function readStamps(): { [string]: number }
	if not fs.isFile(VaultGate.STAMP) then
		return {}
	end
	local ok, decoded = pcall(serde.decode, "json" :: any, fs.readFile(VaultGate.STAMP))
	return if ok and type(decoded) == "table" then decoded else {}
end

-- the department to show for this command, or nil (unmapped command, a lookup, or no vault)
function VaultGate.deptFor(name: string, args: { string }): string?
	local dept = VaultGate.DEPT_OF_COMMAND[name]
	if not dept or not Vault.exists() then
		return nil
	end
	if args[1] and LOOKUP[args[1]] then
		return nil
	end
	return dept
end

-- true when the page should print now (and stamps it), honouring the window and the override
function VaultGate.due(dept: string, window: number?): boolean
	local mode = Config.env("VAULT_PAGE") -- (PARALLAX_VAULT_PAGE, else KIT_VAULT_PAGE)
	if mode == "never" then
		return false
	end
	local stamps = readStamps()
	local minutes = window
	if not minutes then
		local cfg = Config.load()
		minutes = (cfg.vault and tonumber(cfg.vault.reshow_minutes)) or 120
	end
	local last = tonumber(stamps[dept]) or 0
	if mode ~= "always" and now() - last < (minutes :: number) * 60 then
		return false
	end
	stamps[dept] = now()
	if not fs.isDir(".verify") then
		fs.writeDir(".verify")
	end
	pcall(fs.writeFile, VaultGate.STAMP, serde.encode("json", stamps, true))
	return true
end

function VaultGate.before(name: string, args: { string })
	local dept = VaultGate.deptFor(name, args)
	if not dept then
		return
	end
	-- the owner's latest verdicts in this lane's own store reach the vault before the command runs (no manual sync)
	if Vault.STORES_OF[dept] then
		local filed, clean = Vault.catchUp(Vault.STORES_OF[dept])
		if #filed > 0 then
			print(
				`-- the vault caught up: {table.concat(filed, ", ")} filed{if clean
					then ""
					else " (the sync failed: lune run kit vault sync)"}; commit kit/knowledge/vault with your work`
			)
		end
	end
	if not VaultGate.due(dept) then
		return
	end
	local cfg = Config.load()
	print(
		`-- read first: the {dept} department's page (shown once per {(cfg.vault and tonumber(cfg.vault.reshow_minutes)) or 120} min; the full page: lune run kit vault page {dept} --full)`
	)
	print(Vault.page(dept, (cfg.vault and tonumber(cfg.vault.budget)) or 1500))
	print("")
end

return VaultGate

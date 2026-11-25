--!strict
-- FoleyRules.luau — the decisions of the Foley runtime (pure; kit/test/spec/foley.spec.luau): which surface a floor
-- material is, how often a foot falls at a speed, how heavy a step and a landing are, and the sound's name in the
-- footsteps set (assets/sounds/sets/footsteps.json: boot_step_<surface>_<light|heavy>, land_<light|heavy>, cloth_rustle).
local FoleyRules = {}

-- Enum.Material name -> the footsteps set's surface (anything unknown is dirt: the most neutral step)
FoleyRules.SURFACE = {
	Grass = "grass",
	LeafyGrass = "grass",
	Ground = "dirt",
	Mud = "dirt",
	Sand = "sand",
	Snow = "snow",
	Glacier = "snow",
	Ice = "snow",
	Water = "water",
	Rock = "stone",
	Slate = "stone",
	Basalt = "stone",
	Limestone = "stone",
	Sandstone = "stone",
	Cobblestone = "stone",
	Concrete = "stone",
	Brick = "stone",
	Granite = "stone",
	Marble = "stone",
	Pavement = "stone",
	Salt = "stone",
	CrackedLava = "stone",
	Asphalt = "stone",
	Wood = "wood",
	WoodPlanks = "wood",
	Metal = "metal",
	DiamondPlate = "metal",
	CorrodedMetal = "metal",
	Foil = "metal",
}

FoleyRules.RUN_SPEED = 20 -- studs / s from which a step is a run (heavy)
FoleyRules.STRIDE = 5.6 -- studs between footfalls at a walk (R6 / R15 default walk 16 -> 0.35 s)

local function finite(x: unknown): boolean
	return type(x) == "number" and x == x and x ~= math.huge and x ~= -math.huge
end

-- the surface under the feet (nil in the air: no step); `overrides` = a game's own material -> surface (SampleRegion's
-- gold meadow: { Grass = "drygrass" }), anything not a string in it is ignored
function FoleyRules.surface(materialName: unknown, overrides: { [string]: unknown }?): string?
	if type(materialName) ~= "string" or materialName == "Air" then
		return nil
	end
	local o = overrides and overrides[materialName]
	if type(o) == "string" then
		return o
	end
	return FoleyRules.SURFACE[materialName] or "dirt"
end

-- seconds between footfalls at a horizontal speed (nil when standing still)
function FoleyRules.interval(speed: unknown): number?
	if not finite(speed) or (speed :: number) < 2 then
		return nil
	end
	return math.clamp(FoleyRules.STRIDE / (speed :: number), 0.22, 0.6)
end

function FoleyRules.weight(speed: unknown): string
	return if finite(speed) and (speed :: number) >= FoleyRules.RUN_SPEED then "heavy" else "light"
end

-- the step's sound in the footsteps set
function FoleyRules.stepSound(materialName: unknown, speed: unknown, overrides: { [string]: unknown }?): string?
	local s = FoleyRules.surface(materialName, overrides)
	if not s then
		return nil
	end
	return `boot_step_{s}_{FoleyRules.weight(speed)}`
end

-- a landing from a fall at `fallSpeed` studs / s downward: nil below a hop, light, or heavy past a real drop
function FoleyRules.landSound(fallSpeed: unknown): string?
	if not finite(fallSpeed) or (fallSpeed :: number) < 30 then
		return nil
	end
	return if (fallSpeed :: number) >= 60 then "land_heavy" else "land_light"
end

return FoleyRules

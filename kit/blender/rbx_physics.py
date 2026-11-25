"""rbx_physics.py — ROBLOX'S OWN PHYSICS FOR EACH MATERIAL, for a.physics(group, like=<material>): a group that should
weigh, slide and bounce like iron, wood or stone takes the engine's numbers for that material instead of numbers
typed by hand (his V3 list, 3D stage G.2e).

MEASURED in Roblox Studio 2026-11-18 (KitPlaytestScratch, Edit, nothing made: PhysicalProperties.new(Enum.Material.X)
for every material) - (density, friction, elasticity). Roblox's own, not a textbook's: its Wood is 0.35, its Metal
7.85, its Rock 2.69. No Blender, no numpy: tested on its own."""

MATERIALS = {
    "Plastic": (0.7, 0.3, 0.5), "SmoothPlastic": (0.7, 0.2, 0.5), "Neon": (0.7, 0.3, 0.2),
    "Wood": (0.35, 0.48, 0.2), "WoodPlanks": (0.35, 0.48, 0.2), "Marble": (2.563, 0.2, 0.17),
    "Basalt": (2.691, 0.7, 0.15), "Slate": (2.691, 0.4, 0.2), "CrackedLava": (2.691, 0.65, 0.15),
    "Concrete": (2.403, 0.7, 0.2), "Limestone": (2.691, 0.5, 0.15), "Granite": (2.691, 0.4, 0.2),
    "Pavement": (2.691, 0.5, 0.17), "Brick": (1.922, 0.8, 0.15), "Pebble": (2.403, 0.4, 0.17),
    "Cobblestone": (2.691, 0.5, 0.17), "Rock": (2.691, 0.5, 0.17), "Sandstone": (2.691, 0.5, 0.15),
    "CorrodedMetal": (7.85, 0.7, 0.2), "DiamondPlate": (7.85, 0.35, 0.25), "Foil": (2.7, 0.4, 0.25),
    "Metal": (7.85, 0.4, 0.25), "Grass": (0.9, 0.4, 0.1), "LeafyGrass": (0.9, 0.4, 0.1), "Sand": (1.602, 0.5, 0.05),
    "Fabric": (0.7, 0.35, 0.05), "Snow": (0.9, 0.3, 0.03), "Mud": (0.9, 0.3, 0.07), "Ground": (0.9, 0.45, 0.1),
    "Asphalt": (2.36, 0.8, 0.2), "Salt": (2.165, 0.5, 0.05), "Ice": (0.919, 0.02, 0.15), "Glacier": (0.919, 0.05, 0.15),
    "Glass": (2.403, 0.25, 0.2), "Cardboard": (0.7, 0.5, 0.05), "Carpet": (1.1, 0.4, 0.25),
    "CeramicTiles": (2.4, 0.51, 0.2), "ClayRoofTiles": (2.0, 0.51, 0.2), "RoofShingles": (2.36, 0.8, 0.2),
    "Leather": (0.86, 0.35, 0.25), "Plaster": (0.75, 0.6, 0.2), "Rubber": (1.3, 1.5, 0.95),
}
# the words a brief says for them (the engine has one Metal for every metal: a bronze guard weighs like its iron)
ALIASES = {"iron": "Metal", "steel": "Metal", "bronze": "Metal", "brass": "Metal", "copper": "Metal", "gold": "Metal",
           "silver": "Metal", "rust": "CorrodedMetal", "rusted": "CorrodedMetal", "stone": "Rock", "timber": "Wood",
           "plank": "WoodPlanks", "planks": "WoodPlanks", "cloth": "Fabric", "tyre": "Rubber", "tire": "Rubber",
           "tile": "CeramicTiles", "tiles": "CeramicTiles"}


def like(name):
    """a material's name (Roblox's, any case, or a word ALIASES knows) -> (its Roblox name, (density, friction,
    elasticity)); an unknown name is refused, naming the closest ones"""
    key = str(name).strip()
    by_lower = {k.lower(): k for k in MATERIALS}
    real = by_lower.get(key.lower().replace(" ", "")) or ALIASES.get(key.lower())
    if real is None:
        import difflib  # noqa: PLC0415

        near = difflib.get_close_matches(key.lower(), list(by_lower) + list(ALIASES), n=3, cutoff=0.5)
        raise ValueError(f"physics: like={name!r} is not a Roblox material"
                         + (f" (did you mean {', '.join(by_lower.get(n, n) for n in near)}?)" if near else "")
                         + " - one of " + ", ".join(sorted(MATERIALS)))
    return real, MATERIALS[real]

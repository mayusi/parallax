"""housebays.py - where a house's door and windows stand along each wall: ONE rule for the building generator's gaps
and for the mesh that skins it (pure python, no Blender; kit/world/gothic_blender.py's `_house_mesh` cuts by it).

The building generator (kit/lib/world.luau, kind "building") cuts each side like this:
    n = floor((length - 4) / every) bays, bay k (1..n) centred at  -length/2 + (k - 0.5) * length / n
    measured ALONG THE WALL from the corner the wall starts at; the door takes bay ceil(n / 2) of its side on the
    ground floor. n = 0: that side has no opening at all (a front too narrow for a bay has no door).
Its walls start at: N the west corner (running east), E the north corner (running south), S the EAST corner (running
west), W the SOUTH corner (running north).

A skin mesh is modelled with its front to -Y in Blender (Roblox (x, y, z) -> Blender (x, -z, y)), and lays its
bays out from the low end of each wall's own axis (Blender x for N / S, Blender y for E / W). On N and W that is the
generator's start corner; on S and E it is the far one - so there the door's bay is counted from the other end.
With an odd count the middle bay is the middle either way; with an EVEN count the mesh's door stood in the bay the
building keeps a window in (a door behind stone and a window gap behind the door: found 2026-11-13 on a 27-stud
front, by a fresh reader and then in a render; GothicCourtyard's gc_house_b, 24 wide, has it too until it is re-made).
"""

import math

# the sides whose wall the generator starts at the HIGH end of the mesh's own axis
_REVERSED = ("S", "E")


def count(length, every):
    """how many bays a wall of this length has (0 = none: no door, no window)"""
    if every <= 0:
        return 0
    return max(0, int(math.floor((length - 4) / every + 1e-9)))


def centres(length, every):
    """bay centres along the mesh's own axis, low end first, measured from the wall's middle"""
    n = count(length, every)
    return [-length / 2 + (k - 0.5) * length / n for k in range(1, n + 1)]


def door_slot(length, every, side):
    """which of `centres` (1-based) is the door's bay on this side of the mesh; 0 = no bay at all"""
    n = count(length, every)
    if n == 0:
        return 0
    k = int(math.ceil(n / 2))  # the generator's bay, counted from the corner ITS wall starts at
    return n - k + 1 if side in _REVERSED else k

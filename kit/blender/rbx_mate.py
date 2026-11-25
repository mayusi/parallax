"""SOCKETS AND MATES (the owner's limitations, D-R04: "Generated pieces lack reliable functional semantics and an
assembly solver ... Add semantic part identities, sockets and mate/clearance relationships; changing a dimension
should update dependents or report incompatible constraints"; the 3D methods audit, stage L).

A SOCKET is a named place on a part where another part meets it: a point, the direction it faces OUT of its part,
and (for a hole or a pin) how far across it is. A MATE says two sockets meet - seated face to face, or one sliding
along the other's line - and with what clearance. The build then MEASURES: is each socket still on its part's
surface, do the two still meet, does the pin still fit the hole. Pure numbers; rbx.Asset.socket / .mate / .at."""

import math

ON = 0.02          # studs: a socket lies ON its part within this ...
ON_SHARE = 0.01    # ... or this share of the part's largest size, whichever is more
MEET = 0.01        # studs: two seated sockets are at one place within this
TURN = 3.0         # degrees: two directions are "the same line" within this
HOWS = ("seat", "slide")


def unit(v):
    n = math.sqrt(sum(float(c) * float(c) for c in v))
    if n < 1e-12:
        raise ValueError("a socket's direction needs a length")
    return tuple(float(c) / n for c in v)


def on_tolerance(part_size):
    return max(ON, ON_SHARE * float(part_size))


def on_problem(name, part, distance, part_size):
    """a socket that is no longer on its part -> a sentence, or None. distance: from the socket's point to the
    part's nearest surface (studs); None: the part is gone"""
    if distance is None:
        return f'{name}: its part "{part}" is no longer in the model'
    if distance > on_tolerance(part_size):
        return (f'{name}: it lies {distance:.3g} studs off "{part}" - the part changed and the socket did not '
                "follow (say the socket from the same numbers as the part)")
    return None


SIZE_OFF = 0.10    # a socket's given size and what its part measures there differ by more than this share: said
RAYS = 16          # directions round a socket, in the plane across its facing, a hole's or a pin's width is read on


def across(dists):
    """a hole's or a pin's width from RAYS distances read round its middle (evenly turned, in the plane across its
    facing; None where a ray met nothing) -> (width, roundness) or None: each opposite pair's sum, their median
    (a socket a little off the middle still reads the width); roundness = the pairs' spread over that width
    (0 = round)"""
    n = len(dists)
    if n < 4 or n % 2 or any(d is None for d in dists):
        return None
    pairs = sorted(float(dists[k]) + float(dists[k + n // 2]) for k in range(n // 2))
    mid = pairs[len(pairs) // 2] if len(pairs) % 2 else 0.5 * (pairs[len(pairs) // 2 - 1] + pairs[len(pairs) // 2])
    if mid <= 0:
        return None
    return mid, (pairs[-1] - pairs[0]) / mid


def size_problem(name, given, measured, kind):
    """a socket's size said one way and its part measured another -> a sentence, or None"""
    if given is None or measured is None:
        return None
    if abs(float(measured) - float(given)) <= SIZE_OFF * float(given):
        return None
    return (f"{name}: its size is said {float(given):g} studs across, its part measures {float(measured):.3g} "
            f"across there (a {kind}) - say the size from the same numbers as the part, or leave size= out and the "
            "build measures it")


def _angle(a, b):
    d = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    return math.degrees(math.acos(d))


def mate_problem(name, plug, socket, how="seat", fit=None):
    """a mate that does not hold -> a sentence, or None. plug, socket: {"pos", "axis" (unit, out of its part),
    "size" or None}. seat: the two at one place, facing each other. slide: the plug's point on the socket's line,
    the two directions along one line. fit=(least, most): the clearance each side, (socket size - plug size) / 2."""
    if how not in HOWS:
        raise ValueError(f"mate: how={how!r} - one of {', '.join(HOWS)}")
    d = tuple(p - s for p, s in zip(plug["pos"], socket["pos"]))
    apart = math.sqrt(sum(c * c for c in d))
    facing = _angle(plug["axis"], tuple(-c for c in socket["axis"]))
    said = []
    if how == "seat":
        if apart > MEET:
            said.append(f"they are {apart:.3g} studs apart")
        if facing > TURN:
            said.append(f"they do not face each other ({facing:.3g} degrees off)")
    else:
        along = sum(x * y for x, y in zip(d, socket["axis"]))
        side = math.sqrt(max(apart * apart - along * along, 0.0))
        if side > MEET:
            said.append(f"the plug is {side:.3g} studs off the socket's line")
        if min(facing, 180.0 - facing) > TURN:
            said.append(f"their directions are not one line ({min(facing, 180.0 - facing):.3g} degrees off)")
    if fit is not None:
        if plug.get("size") is None or socket.get("size") is None:
            said.append("fit= needs a size on both sockets")
        else:
            least, most = (float(v) for v in fit)
            room = (float(socket["size"]) - float(plug["size"])) / 2.0
            if room < least - 1e-9:
                said.append(f"the plug ({plug['size']:g} across) has {room:.3g} studs of room each side in "
                            f"{socket['size']:g}, under the {least:g} asked" if room >= 0 else
                            f"the plug ({plug['size']:g} across) does not go into {socket['size']:g}")
            elif room > most + 1e-9:
                said.append(f"the plug ({plug['size']:g} across) rattles: {room:.3g} studs of room each side in "
                            f"{socket['size']:g}, over the {most:g} asked")
    return f"{name}: " + "; ".join(said) if said else None

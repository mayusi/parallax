"""sky.py - A SKY OF THE KIT'S OWN, face by face (the owner's method list: "Skyboxes"; pure, no Blender).
Roblox draws a sky from six square images, one a face of a cube round the camera: SkyboxFt, Bk, Lf, Rt, Up, Dn. Its
page does not say which way each face looks. MEASURED in Roblox Studio (2026-11-15, the kit's scratch place, built-in
textures as the six faces, no upload):
    Ft is seen looking toward -Z, upright, not mirrored        Lf is seen looking toward +X, upright
    Up: the image's TOP edge lies toward +X                    Dn: the image's TOP edge lies toward -X
(Bk and Rt were not looked at: by their names they are the faces opposite Ft and Lf.)
So each face is what a camera at the middle sees with a square 90-degree view: its look and its up are the table
below. kit/world/sky_blender.py renders them; this file is what needs no Blender: the faces, where a direction falls
in which face's picture, where the sun stands, the command's words."""
import math

# face -> (the way the camera looks, the way its picture's top edge lies), Roblox space (y up)
FACES = {
    "ft": ((0, 0, -1), (0, 1, 0)),
    "bk": ((0, 0, 1), (0, 1, 0)),
    "lf": ((1, 0, 0), (0, 1, 0)),
    "rt": ((-1, 0, 0), (0, 1, 0)),
    "up": ((0, 1, 0), (1, 0, 0)),
    "dn": ((0, -1, 0), (-1, 0, 0)),
}
# face -> the Sky object's property
PROPERTY = {"ft": "SkyboxFt", "bk": "SkyboxBk", "lf": "SkyboxLf", "rt": "SkyboxRt", "up": "SkyboxUp", "dn": "SkyboxDn"}


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def right(face):
    """the way a face's picture's RIGHT edge lies (look x up: the picture is seen from inside, not mirrored)"""
    look, up = FACES[face]
    return cross(look, up)


def sun_vector(elevation, azimuth):
    """where the sun stands: `elevation` degrees over the horizon, `azimuth` degrees round from -Z (the kit's north)
    toward +X (east) -> a unit vector toward it, Roblox space"""
    e, a = math.radians(elevation), math.radians(azimuth)
    return (math.sin(a) * math.cos(e), math.sin(e), -math.cos(a) * math.cos(e))


def falls(direction):
    """WHERE A DIRECTION FALLS: the face whose picture shows it and the place in that picture -> (face, u, v) with u
    0..1 from the picture's left edge to its right, v 0..1 from its TOP edge down"""
    best, most = None, -math.inf
    for face, (look, _) in FACES.items():
        along = dot(direction, look)
        if along > most:
            best, most = face, along
    look, up = FACES[best]
    x = dot(direction, right(best)) / most
    y = dot(direction, up) / most
    return best, (x + 1) / 2, (1 - y) / 2


def direction(face, u, v):
    """... and back: the way a place in a face's picture points -> a unit vector, Roblox space"""
    look, up = FACES[face]
    r = right(face)
    x, y = u * 2 - 1, 1 - v * 2
    d = [look[i] + r[i] * x + up[i] * y for i in range(3)]
    length = math.sqrt(dot(d, d))
    return tuple(c / length for c in d)


def apart(a, b):
    """the angle between two directions, in degrees"""
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(a, b) / math.sqrt(dot(a, a) * dot(b, b))))))


# THE CHECK'S SUNS: one test sun for each face, well off its middle and off its diagonals (a camera turned a
# quarter or mirrored puts it elsewhere in its picture) -> {face: a unit vector}
def test_suns():
    return {face: direction(face, 0.74, 0.31) for face in FACES}


def to_blender(p):
    """Roblox (x, y up, z) -> Blender (x, y, z up): a quarter turn about x, no mirror"""
    return (p[0], -p[2], p[1])


def camera_matrix(face):
    """the face's camera as Blender wants it: the rows of a 3 x 3 turn whose columns are the camera's right, its up and
    the way BEHIND it (a Blender camera looks down its own -z), in Blender space"""
    look, up = FACES[face]
    r, u, back = to_blender(right(face)), to_blender(up), to_blender(tuple(-c for c in look))
    return [[r[i], u[i], back[i]] for i in range(3)]


WORDS = ("--name", "--sun", "--clouds", "--seed", "--size", "--ridges", "--ridge-height")


# FAR RIDGES (the owner's method list: "Matte painting"): ranges of mountains PAINTED into the sky's pictures, one
# behind the other. The farthest is the highest and the palest (the air between); each nearer one is lower and darker.
# A range's crest at a compass side is some share of its top, by noise round the horizon.
def ridge_layers(count, height):
    """the ranges of a sky, farthest first -> [{"top": degrees, "low": degrees, "air": 0..1, "scale": noise}]:
    top = the highest a crest of this range can stand, low = the lowest, air = how far it fades into the horizon's haze"""
    out = []
    for i in range(count):
        near = i / max(count - 1, 1) if count > 1 else 0.0  # (0 = the farthest, 1 = the nearest)
        top = height * (1.0 - 0.5 * near)
        out.append({"top": round(top, 4), "low": round(top * 0.35, 4), "air": round(0.75 - 0.5 * near, 4),
                    "scale": round(2.2 + 2.6 * near, 4)})
    return out


def elevation(direction):
    """how many degrees a way stands over the horizon (Roblox's axes: y up)"""
    x, y, z = direction
    return math.degrees(math.atan2(y, math.hypot(x, z)))


def compass(direction):
    """the compass side of a way: degrees from -Z round toward +X, 0..360"""
    return math.degrees(math.atan2(direction[0], -direction[2])) % 360.0


def arguments(argv):
    """the command's words -> (settings, None) or (None, why)
       <out_dir> --name <Name> [--sun elevation,azimuth] [--clouds 0..1] [--seed n] [--size 256|512|1024]
                 [--ridges 0..3] [--ridge-height 2..25]"""
    use = ("usage: <out_dir> --name <Name> [--sun <elevation>,<azimuth>] [--clouds 0..1] [--seed n] [--size 256|512|1024] "
           "[--ridges 0..3] [--ridge-height 2..25]")
    if len(argv) < 1 or argv[0].startswith("--"):
        return None, use
    s = {"out": argv[0], "name": None, "sun": (35.0, 135.0), "clouds": 0.4, "seed": 1, "size": 512, "ridges": 0,
         "ridge_height": None}
    k = 1
    said = set()
    while k < len(argv):
        word = argv[k]
        if word not in WORDS or k + 1 >= len(argv):
            return None, f"sky: {word} is not a word it knows ({', '.join(WORDS)}), or has no value"
        value = argv[k + 1]
        k += 2
        if word in said:
            return None, f"sky: {word} is said twice"
        said.add(word)
        if word == "--name":
            if not value or not all((c.isascii() and c.isalnum()) or c == "_" for c in value):
                return None, f"sky: --name is the sky's name (letters, digits, _) (got {value})"
            s["name"] = value
            continue
        try:
            numbers = [float(v) for v in value.split(",")]
        except ValueError:
            return None, f"sky: {word} is a number (got {value})"
        if any(n != n or n in (math.inf, -math.inf) for n in numbers):
            return None, f"sky: {word} is a number (got {value})"
        if word == "--sun":
            if len(numbers) != 2 or not -10 <= numbers[0] <= 90 or not 0 <= numbers[1] < 360:
                return None, f"sky: --sun is <elevation -10..90>,<azimuth 0..360 from -Z toward +X> (got {value})"
            s["sun"] = (numbers[0], numbers[1])
        elif len(numbers) != 1:
            return None, f"sky: {word} is one number (got {value})"
        elif word == "--clouds":
            if not 0 <= numbers[0] <= 1:
                return None, f"sky: --clouds is 0 (clear) to 1 (overcast) (got {value})"
            s["clouds"] = numbers[0]
        elif word == "--seed":
            if numbers[0] % 1 != 0 or not 0 <= numbers[0] <= 65535:
                return None, f"sky: --seed is a whole number 0 to 65535 (got {value})"
            s["seed"] = int(numbers[0])
        elif word == "--ridges":
            if numbers[0] not in (0, 1, 2, 3):
                return None, f"sky: --ridges is how many ranges of far mountains stand on the horizon, 0 to 3 (got {value})"
            s["ridges"] = int(numbers[0])
        elif word == "--ridge-height":
            if not 2 <= numbers[0] <= 25:
                return None, f"sky: --ridge-height is how many degrees the highest crest stands over the horizon, 2 to 25 (got {value})"
            s["ridge_height"] = numbers[0]
        else:
            if numbers[0] not in (256, 512, 1024):
                return None, f"sky: --size is 256, 512 or 1024 (got {value})"
            s["size"] = int(numbers[0])
    if s["name"] is None:
        return None, "sky: --name says what the sky is called"
    if s["ridge_height"] is not None and s["ridges"] == 0:
        return None, "sky: --ridge-height is the height of ridges, and there are none (--ridges 1..3)"
    if s["ridges"] > 0 and s["ridge_height"] is None:
        s["ridge_height"] = 8.0
    return s, None

"""rbx_firearm.py — guns that look like guns: real proportions + well-made parts, for any model.

Why this exists: drawing a rifle from imagination with coordinates gives toy proportions (a huge grip, a short
body, a stubby barrel, a can for a magazine). Real firearms follow tight ratios. This module holds them, plus a
part library (receiver, barrel, muzzle, handguard, stock, grip, magazine, optic, bipod...) built with chamfers,
tapers, cut details and rails — so a build script picks a KIND, a STYLE and PART VARIANTS, then adds its own
custom details on top. Everything it makes is a normal named part (a.cut / a.expect / extra parts all work).

    import rbx, rbx_firearm as F
    a = rbx.Asset("marksman", ground=False)
    gun = F.Firearm(a, "sniper", length=4.6, style="military")    # palette + proportions + default parts
    gun.set(stock="thumbhole", muzzle="brake", optic="scope", bipod=True)
    gun.build()                     # named parts + anchors (Muzzle, Sight, Grip) + proportion checks
    a.box("Patch", (0.02, 0.1, 0.3), gun.at(0.45, 0.0, side=1), "accent")   # your own details on top
    a.build()

Coordinates: the ORIGIN is the middle of the pistol grip (where the hand holds) — so in game Models.tool(...)
needs no Grip offset. Front = -Z, up = +Y. gun.at(u, h, side) converts a design position to studs:
u = 0 (butt) .. 1 (muzzle) along the gun, h = height above the bore in gun-lengths, side = -1 left / 1 right.
"""

import math

# ---------------------------------------------------------------------------------------------- proportions
# Fractions of the overall length L (butt = 0 .. muzzle = 1). Heights are fractions of L above the bore line.
# Sources: published dimensions of real rifles (AWM/M24 bolt actions, AR-15/M4 family, MP5-class SMGs,
# pump shotguns), stylised ~15% chunkier for Roblox readability. RANGES are what the checks allow.
KINDS = {
    "sniper": {
        "length": 4.6,
        "grip_u": 0.35,  # where the hand holds (origin)
        "receiver": (0.345, 0.565),
        "receiver_h": (-0.032, 0.034),
        "width": 0.048,
        "barrel_end": 0.945,
        "barrel_r": (0.0125, 0.0095),
        "handguard": (0.565, 0.80),
        "stock": (0.0, 0.35),
        "butt_h": (-0.1, 0.036),
        "grip_rake": 16,
        "grip_len": 0.105,
        "mag": (0.425, 0.485, -0.085),
        "optic_h": 0.078,
        "parts": {
            "stock": "thumbhole",
            "muzzle": "brake",
            "handguard": "slotted",
            "optic": "scope",
            "mag": "box",
            "bipod": True,
            "bolt": True,
            "rail": True,
        },
    },
    "assault": {
        "length": 3.8,
        "grip_u": 0.37,
        "receiver": (0.30, 0.60),
        "receiver_h": (-0.03, 0.042),
        "width": 0.05,
        "barrel_end": 0.95,
        "barrel_r": (0.011, 0.009),
        "handguard": (0.60, 0.88),
        "stock": (0.0, 0.31),
        "butt_h": (-0.12, 0.035),
        "grip_rake": 20,
        "grip_len": 0.115,
        "mag": (0.445, 0.51, -0.165),
        "optic_h": 0.07,
        "parts": {
            "stock": "collapsible",
            "muzzle": "flash_hider",
            "handguard": "railed",
            "optic": "reddot",
            "mag": "curved",
            "bipod": False,
            "bolt": False,
            "rail": True,
        },
    },
    "smg": {
        "length": 2.6,
        "grip_u": 0.42,
        "receiver": (0.30, 0.78),
        "receiver_h": (-0.04, 0.05),
        "width": 0.06,
        "barrel_end": 0.95,
        "barrel_r": (0.013, 0.012),
        "handguard": (0.62, 0.88),
        "stock": (0.0, 0.31),
        "butt_h": (-0.13, 0.04),
        "grip_rake": 18,
        "grip_len": 0.15,
        "mag": (0.52, 0.59, -0.26),
        "optic_h": 0.085,
        "parts": {
            "stock": "folding",
            "muzzle": "suppressor",
            "handguard": "railed",
            "optic": "holo",
            "mag": "curved",
            "bipod": False,
            "bolt": False,
            "rail": True,
        },
    },
    # long, boxy energy rifle (modern sci-fi shooter look): one armoured body from butt to a chamfered nose,
    # heat-sink fins on top, clamp bands, inset panels, light strips; built by Firearm._railgun
    "railgun": {
        "length": 5.2,
        "grip_u": 0.265,
        "receiver": (0.28, 0.47),
        "receiver_h": (-0.04, 0.05),
        "width": 0.056,
        "barrel_end": 1.0,
        "barrel_r": (0.012, 0.012),
        "handguard": (0.48, 0.7),
        "stock": (0.0, 0.24),
        "butt_h": (-0.075, 0.075),
        "grip_rake": 8,
        "grip_len": 0.095,
        "mag": (0.352, 0.497, -0.075),
        "optic_h": 0.115,
        "front_stretch": 1.0,  # >1 lengthens everything ahead of stretch_from (a longer, sleeker front)
        "stretch_from": 0.58,
        "parts": {
            "stock": "frame",
            "muzzle": "none",
            "handguard": "none",
            "optic": "hooded",
            "mag": "drum",
            "bipod": False,
            "bolt": False,
            "rail": False,
        },
    },
    "shotgun": {
        "length": 4.0,
        "grip_u": 0.33,
        "receiver": (0.32, 0.52),
        "receiver_h": (-0.045, 0.035),
        "width": 0.05,
        "barrel_end": 1.0,
        "barrel_r": (0.0135, 0.0135),
        "handguard": (0.58, 0.76),
        "stock": (0.0, 0.33),
        "butt_h": (-0.13, -0.006),  # a hunting-style drop: the butt sits below the bore line
        "grip_rake": 16,
        "grip_len": 0.11,
        "mag": None,
        "optic_h": 0.05,
        "parts": {
            "stock": "solid",
            "muzzle": "none",
            "handguard": "pump",
            "optic": "irons",
            "mag": "tube",
            "bipod": False,
            "bolt": False,
            "rail": False,
        },
    },
}

STYLES = {
    # Physically based (rbx_pbr: the pbr_values gate): a gun's dark finishes are COATINGS (parkerizing, cerakote,
    # anodizing, lacquer) — metal 0 with a dark base; only machined / bright steel is bare metal (metal 1, base 160-250
    # sRGB). Chips and wear reveal the bare metal underneath (`under`, metal 1).
    "dark": {  # gunmetal black + slate-blue panels + orange light (the "Reaper" sci-fi look)
        "frame": dict(color=(0.06, 0.062, 0.068), metal=0.0, rough=0.42, wear=0.2, chip=0.45, under=(0.5, 0.51, 0.53), grime=0.45, pattern="coat"),
        "steel": dict(color=(0.413, 0.4, 0.385), metal=1.0, rough=0.48, wear=0.3, grime=0.3, pattern="brushed"),  # dark steel: rough, so it reads dark
        "bright": dict(color=(0.5, 0.51, 0.53), metal=1.0, rough=0.26, wear=0.1, pattern="brushed"),  # machined ends
        "gloss": dict(color=(0.035, 0.037, 0.041), metal=0.0, rough=0.13, wear=0.05),  # gloss black lacquer (scope)
        "polished": dict(color=(0.045, 0.046, 0.05), metal=0.0, rough=0.2, wear=0.08, pattern="brushed"),  # polished black coat (drum)
        "polymer": dict(color=(0.05, 0.05, 0.055), metal=0.0, rough=0.7, wear=0.1, grime=0.5),
        "furniture": dict(color=(0.22, 0.26, 0.33), metal=0.0, rough=0.38, wear=0.05, chip=0.4, under=(0.5, 0.51, 0.53), grime=0.25),  # slate-blue panels: smooth (a weave read as a maze in the region close-ups)
        "trim": dict(color=(0.04, 0.041, 0.045), metal=0.0, rough=0.5),  # black-oxide hardware
        "rubber": dict(color=(0.033, 0.033, 0.035), metal=0.0, rough=0.9, pattern="grid"),
        "glass": dict(color=(0.06, 0.12, 0.1), metal=0.0, rough=0.04, alpha=0.75),
        "glow": dict(color=(1.0, 0.22, 0.05), metal=0.0, rough=0.4, emit=4.0),
        "decal": dict(color=(0.72, 0.72, 0.7), metal=0.0, rough=0.6),  # printed white, not paper white
    },
    # name: material definitions handed to a.material (name -> kwargs); "trim" = small hardware
    "military": {
        "frame": dict(color=(0.13, 0.135, 0.14), metal=0.0, rough=0.5, wear=0.25),  # parkerized / cerakote grey
        "steel": dict(color=(0.413, 0.4, 0.385), metal=1.0, rough=0.48),  # bare steel (barrel, bolt): rough dark steel
        "polymer": dict(color=(0.085, 0.085, 0.09), metal=0.0, rough=0.78, wear=0.15),
        "furniture": dict(color=(0.34, 0.30, 0.22), metal=0.0, rough=0.7, wear=0.2),  # tan stock / handguard
        "trim": dict(color=(0.06, 0.06, 0.065), metal=0.0, rough=0.5),  # black-oxide hardware
        "rubber": dict(color=(0.045, 0.045, 0.045), metal=0.0, rough=0.92),
        "glass": dict(color=(0.08, 0.2, 0.24), metal=0.0, rough=0.04, alpha=0.75),
        "glow": dict(color=(1.0, 0.25, 0.15), metal=0.0, rough=0.4, emit=3.0),
    },
    "scifi": {
        "frame": dict(color=(0.82, 0.84, 0.87), metal=0.0, rough=0.38, wear=0.15),  # white armour panels
        "steel": dict(color=(0.48, 0.5, 0.54), metal=1.0, rough=0.25),  # machined steel
        "polymer": dict(color=(0.11, 0.12, 0.14), metal=0.0, rough=0.6),
        "furniture": dict(color=(0.16, 0.17, 0.2), metal=0.0, rough=0.5),
        "trim": dict(color=(0.07, 0.075, 0.085), metal=0.0, rough=0.45),
        "rubber": dict(color=(0.05, 0.05, 0.055), metal=0.0, rough=0.9),
        "glass": dict(color=(0.1, 0.55, 0.7), metal=0.0, rough=0.04, alpha=0.7),
        "glow": dict(color=(0.25, 0.9, 1.0), metal=0.0, rough=0.3, emit=4.0),
    },
}

VARIANTS = {
    "stock": ("thumbhole", "solid", "collapsible", "folding", "frame", "none"),
    "muzzle": ("brake", "flash_hider", "suppressor", "emitter", "none"),
    "handguard": ("slotted", "railed", "pump", "shroud", "none"),
    "optic": ("scope", "compact", "tactical", "hooded", "reddot", "holo", "irons", "digital", "none"),
    "mag": ("box", "curved", "drum", "tube", "none"),
}

# what the proportion checks allow (fractions of L) — outside = a warning with the exact fix
RANGES = {
    # barrel showing past the handguard (or the receiver, without one)
    "barrel_exposed": {"sniper": (0.1, 0.35), "assault": (0.04, 0.2), "smg": (0.0, 0.15), "shotgun": (0.15, 0.5), "railgun": (0.3, 0.65)},
    "grip_len": (0.08, 0.17),
    "grip_rake": (8, 28),
    "stock_len": (0.22, 0.38),
    "receiver_len": (0.18, 0.5),
}


class Firearm:
    def __init__(self, a, kind="assault", length=None, style="military", palette=None, chunk=1.0):
        """kind: sniper | assault | smg | shotgun. length: overall studs (default per kind — an R6 is 5 tall).
        style: military | scifi (palette + detailing). palette: {material: {...}} overrides.
        chunk: thickness multiplier (1.0 = stylised-real; 1.2 = toy-chunky; 0.9 = sleek)."""
        if kind not in KINDS:
            raise ValueError(f'firearm kind "{kind}" — use one of {", ".join(KINDS)}')
        if style not in STYLES:
            raise ValueError(f'firearm style "{style}" — use one of {", ".join(STYLES)}')
        self.a = a
        self.kind = kind
        self.k = dict(KINDS[kind])
        self.L = float(length or self.k["length"])
        self.style = style
        self.chunk = chunk
        self.parts = dict(self.k["parts"])
        self.m = {}
        mats = {name: dict(spec) for name, spec in STYLES[style].items()}
        for name, spec in (palette or {}).items():
            mats.setdefault(name, {}).update(spec)
        for name, spec in mats.items():
            mname = f"gun_{name}"
            a.material(mname, **spec)
            self.m[name] = mname
        self.grip_h = None  # set once the grip is placed
        self.muzzle_h = 0.0  # muzzle height above the bore (railgun: the emitter sits low in the nose)
        self.sight_h = None
        if not a.design.get("size"):
            a.design["size"] = (0, 0, self.L)  # length is the decision; width/height follow the proportions

    # ------------------------------------------------------------------ design space -> studs
    def _warp(self, u):
        s0, f = self.k.get("stretch_from", 1.0), self.k.get("front_stretch", 1.0)
        return u if u <= s0 else s0 + (u - s0) * f

    def U(self, u):
        """design u (0 butt .. 1 muzzle) -> studs FORWARD of the grip point (extrude 'side' u axis).
        front_stretch warps everything ahead of stretch_from longer (outlines follow; use zs() for lengths)."""
        return (self._warp(u) - self._warp(self.k["grip_u"])) * self.L

    def zs(self, u0, u1):
        """the length in studs of the design span u0..u1 (honours front_stretch — never write (u1 - u0) * L)."""
        return self.U(u1) - self.U(u0)

    def V(self, h):
        """design height (fraction of L above the bore) -> studs above the grip point."""
        return (h - self._grip_h()) * self.L

    def _grip_h(self):
        if self.grip_h is None:
            # the hand holds the grip halfway down its length, below the receiver
            r0 = self.k["receiver_h"][0]
            self.grip_h = r0 - self.k["grip_len"] * 0.5 * math.cos(math.radians(self.k["grip_rake"]))
        return self.grip_h

    def at(self, u, h, side=0.0):
        """design (u, h, side) -> Roblox (x, y, z) studs. side: -1 left face .. 1 right face of the receiver."""
        return (side * self.w(self.k["width"]) / 2, self.V(h), -self.U(u))

    def w(self, frac):
        return frac * self.L * self.chunk

    def outline(self, pts):
        """[(u, h) | (u, h, r)] design -> extrude 'side' outline in studs (r = corner radius as a fraction of L)."""
        out = []
        for p in pts:
            q = (self.U(p[0]), self.V(p[1]))
            out.append(q + ((p[2] * self.L,) if len(p) > 2 else ()))
        return out

    def set(self, **parts):
        """Choose part variants: stock/muzzle/handguard/optic/mag (see VARIANTS), bipod/bolt/rail True|False."""
        for key, value in parts.items():
            if key in VARIANTS and value not in VARIANTS[key]:
                raise ValueError(f'{key}="{value}" — use one of {", ".join(VARIANTS[key])}')
            if key not in VARIANTS and key not in ("bipod", "bolt", "rail"):
                raise ValueError(f'unknown part "{key}" — parts: {", ".join(list(VARIANTS) + ["bipod", "bolt", "rail"])}')
            self.parts[key] = value
        return self

    def tune(self, **dims):
        """Adjust proportions (fractions of L): barrel_end, receiver=(u0, u1), grip_rake, grip_len, optic_h, ...
        Out-of-range values still build, but the proportion checks will warn with the fix."""
        for key, value in dims.items():
            if key not in self.k:
                raise ValueError(f'unknown dimension "{key}" — known: {", ".join(k for k in self.k if k != "parts")}')
            self.k[key] = value
        self.grip_h = None
        return self

    # ------------------------------------------------------------------ build
    def build(self):
        a, k, p = self.a, self.k, self.parts
        if self.kind == "railgun":
            return self._finish(self._railgun())
        self._receiver()
        self._barrel()
        if p["muzzle"] != "none":
            getattr(self, f"_muzzle_{p['muzzle']}")()
        if p["handguard"] != "none":
            getattr(self, f"_handguard_{p['handguard']}")()
        if p["stock"] != "none":
            getattr(self, f"_stock_{p['stock']}")()
        self._grip()
        self._trigger()
        if p["mag"] != "none":
            getattr(self, f"_mag_{p['mag']}")()
        if p["rail"]:
            self._rail(k["receiver"][0] - 0.015, k["receiver"][1] + (0.04 if self.kind == "sniper" else 0.0))
        if p["optic"] != "none":
            getattr(self, f"_optic_{p['optic']}")()
        if p["bolt"]:
            self._bolt()
        if p["bipod"]:
            self._bipod()
        if self.style == "scifi":
            self._scifi_detail()
        return self._finish(self)

    def _finish(self, _):
        a, k, p = self.a, self.k, self.parts
        # lights + markings get their own mesh and texture ("marks"): tiny glyphs and light strips are a few
        # texels in the body's shared texture and bake as smears (the kit's texel check fails them)
        small_colour = {self.m["glow"], self.m.get("decal", "")}
        for i, (o, g) in enumerate(a.parts):
            if g == "main" and o.data.materials and o.data.materials[0].name.endswith(tuple(small_colour - {""})):
                a.parts[i] = (o, "marks")
        tip = getattr(self, "muzzle_at", None)
        a.anchor("Muzzle", (0, self.V(self.muzzle_h), -(tip if tip is not None else self.U(self.muzzle_u))))
        a.anchor("Grip", (0, 0, 0))
        # where the other hand holds (under the handguard / forend) — first-person arms reach for it
        hg = k["handguard"] if (p["handguard"] != "none" or self.kind == "railgun") else (k["receiver"][1] - 0.05, k["receiver"][1])
        a.anchor("Support", (0, self.V(-0.045), -self.U(hg[0] + (hg[1] - hg[0]) * 0.35)))
        if self.sight_h is not None:
            a.anchor("Sight", (0, self.V(self.sight_h), -self.U(k["receiver"][0] - 0.02)))
        self._checks()
        return self

    # ------------------------------------------------------------------ parts
    def _receiver(self):
        a, k = self.a, self.k
        u0, u1 = k["receiver"]
        h0, h1 = k["receiver_h"]
        c = 0.006  # chamfer
        if self.kind == "assault" or self.kind == "smg":
            # upper (bore line) + lower (grip / mag well), the AR silhouette
            mid = h0 + (h1 - h0) * 0.42
            line_h = mid + 0.012
            a.extrude(
                "Receiver",
                self.outline([(u0, mid), (u0, h1 - c, c), (u0 + 0.02, h1), (u1, h1, c * 0.5), (u1, mid)]),
                self.w(k["width"]),
                self.m["frame"],
                bevel=0.012,
            )
            a.extrude(
                "LowerReceiver",
                self.outline(
                    [
                        (u0 + 0.02, mid + 0.001),
                        (u1 - 0.05, mid + 0.001),
                        (u1 - 0.07, h0 - 0.022, c),
                        (u0 + 0.10, h0 - 0.022, c),
                        (u0 + 0.06, h0, c),
                        (u0 + 0.02, h0 + 0.004),
                    ]
                ),
                self.w(k["width"] * 0.9),
                self.m["frame"],
                bevel=0.012,
            )
            # ejection port + forward assist bump on the right
            a.cut(
                "Receiver",
                a.box(
                    "EjectionPort",
                    (self.w(0.02), (h1 - mid) * self.L * 0.45, (u1 - u0) * self.L * 0.25),
                    self.at(u0 + (u1 - u0) * 0.55, (mid + h1) / 2, side=1),
                    self.m["trim"],
                    bevel=0,
                ),
            )
        else:
            line_h = h0 + 0.012
            a.extrude(
                "Receiver",
                self.outline(
                    [
                        (u0, h0 + c, c),
                        (u0, h1 - 0.008, 0.008),
                        (u0 + 0.025, h1),
                        (u1 - 0.01, h1, c),
                        (u1, h1 - 0.012),
                        (u1, h0 + 0.006, c),
                        (u1 - 0.02, h0),
                        (u0 + 0.02, h0, c),
                    ]
                ),
                self.w(k["width"]),
                self.m["frame"],
                bevel=0.012,
            )
            a.cut(
                "Receiver",
                a.box(
                    "EjectionPort",
                    (self.w(0.02), (h1 - h0) * self.L * 0.35, (u1 - u0) * self.L * 0.3),
                    self.at(u0 + (u1 - u0) * 0.42, h0 + (h1 - h0) * 0.62, side=1),
                    self.m["trim"],
                    bevel=0,
                ),
            )
        # side panel line both sides (breaks the big flat face)
        for s, nm in ((1, "R"), (-1, "L")):
            a.cut(
                "Receiver",
                a.box(
                    f"ReceiverLine{nm}",
                    (self.w(0.008), 0.012, (u1 - u0) * self.L * 0.8),
                    self.at((u0 + u1) / 2, line_h, side=s),
                    self.m["trim"],
                    bevel=0,
                ),
            )
        self.sight_h = None

    def _barrel(self):
        a, k = self.a, self.k
        r0, r1 = (r * self.L * self.chunk for r in k["barrel_r"])
        start = k["handguard"][0] - 0.01 if self.parts["handguard"] != "none" else k["receiver"][1] - 0.005
        end = k["barrel_end"]
        self.muzzle_u = end
        z0, z1 = -self.U(start), -self.U(end)
        y = self.V(0)
        a.loft(
            "Barrel",
            [(z0, r0, r0, (0, y)), (z0 + (z1 - z0) * 0.25, r0 * 0.97, r0 * 0.97, (0, y)), (z1, r1, r1, (0, y))],
            self.m["steel"],
            axis="Z",
            segments=14,
        )
        a.cut("Barrel", a.cylinder("BoreCut", r1 * 0.45, 0.2, (0, y, z1), self.m["trim"], axis="Z", segments=10, bevel=0))

    def _muzzle_brake(self):
        a, k = self.a, self.k
        u1 = k["barrel_end"]
        length = 0.06
        self.muzzle_u = u1 + length * 0.9
        r = k["barrel_r"][1] * self.L * self.chunk * 1.9
        zc = -self.U(u1 + length * 0.4)
        y = self.V(0)
        a.extrude(
            "Muzzle",
            [(-r, -r * 0.8, r * 0.3), (r, -r * 0.8, r * 0.3), (r, r * 0.8, r * 0.3), (-r, r * 0.8, r * 0.3)],
            length * self.L,
            self.m["steel"],
            plane="front",
            pos=(0, y, zc),
            bevel=0.01,
        )
        for i in range(3):
            uz = zc - length * self.L * (0.3 - i * 0.22)
            a.cut("Muzzle", a.box(f"MuzzlePort{i}", (r * 2.4, r * 0.9, length * self.L * 0.13), (0, y, uz), self.m["trim"], bevel=0))

    def _muzzle_flash_hider(self):
        a, k = self.a, self.k
        u1 = k["barrel_end"]
        length = 0.05
        self.muzzle_u = u1 + length
        r = k["barrel_r"][1] * self.L * self.chunk * 1.45
        zc = -self.U(u1 + length / 2)
        y = self.V(0)
        a.cylinder("Muzzle", r, length * self.L, (0, y, zc), self.m["trim"], axis="Z", segments=12, bevel=0.006)
        for i, ang in enumerate((0, 60, 120)):
            a.cut(
                "Muzzle",
                a.box(
                    f"MuzzleSlot{i}",
                    (r * 2.4, r * 0.28, length * self.L * 0.5),
                    (0, y, zc - length * self.L * 0.3),
                    self.m["trim"],
                    rot=(0, 0, ang),
                    bevel=0,
                ),
            )

    def _muzzle_suppressor(self):
        a, k = self.a, self.k
        u1 = k["barrel_end"]
        length = 0.22
        self.muzzle_u = u1 + length * 0.85
        r = k["barrel_r"][1] * self.L * self.chunk * 2.3
        z0 = -self.U(u1 - length * 0.15)
        z1 = -self.U(u1 + length * 0.85)
        y = self.V(0)
        a.loft(
            "Muzzle",
            [(z0, r * 0.7, r * 0.7, (0, y)), (z0 - 0.04, r, r, (0, y)), (z1 + 0.04, r, r, (0, y)), (z1, r * 0.8, r * 0.8, (0, y))],
            self.m["trim"],
            axis="Z",
            segments=16,
        )

    def _handguard_slotted(self):
        a, k = self.a, self.k
        u0, u1 = k["handguard"]
        top, bot = 0.024, -0.04
        a.extrude(
            "Handguard",
            self.outline([(u0, top), (u1 - 0.03, top, 0.008), (u1, top - 0.012), (u1, bot + 0.012, 0.006), (u1 - 0.05, bot + 0.004), (u0, bot, 0.006)]),
            self.w(k["width"] * 1.08),
            self.m["furniture"] if self.style == "military" else self.m["frame"],
            bevel=0.014,
        )
        # the barrel channel, then lightening slots on both sides
        a.cut(
            "Handguard",
            a.cylinder("BarrelChannel", k["barrel_r"][0] * self.L * self.chunk * 1.35, (u1 - u0) * self.L + 0.2, (0, self.V(0), -self.U((u0 + u1) / 2)), self.m["trim"], axis="Z", segments=14, bevel=0),
        )
        n = 3
        for i in range(n):
            uc = u0 + (u1 - u0) * (0.22 + i * 0.25)
            a.cut(
                "Handguard",
                a.extrude(
                    f"HandguardSlot{i}",
                    self.outline([(uc - 0.04, -0.006, 0.005), (uc + 0.04, -0.006, 0.005), (uc + 0.04, -0.02, 0.005), (uc - 0.04, -0.02, 0.005)]),
                    self.w(k["width"] * 1.3),
                    self.m["trim"],
                    bevel=0,
                ),
            )

    def _handguard_railed(self):
        a, k = self.a, self.k
        u0, u1 = k["handguard"]
        r = 0.032 * self.chunk
        z0, z1 = -self.U(u0), -self.U(u1)
        y = self.V(0.002)
        a.loft(
            "Handguard",
            [(z0, r * self.L, r * self.L, (0, y)), (z1 + 0.05, r * self.L, r * self.L, (0, y)), (z1, r * self.L * 0.9, r * self.L * 0.9, (0, y))],
            self.m["frame"] if self.style == "scifi" else self.m["polymer"],
            axis="Z",
            segments=8,
        )
        for i in range(4):
            uc = u0 + (u1 - u0) * (0.18 + i * 0.2)
            for s, nm in ((1, "R"), (-1, "L")):
                a.cut(
                    "Handguard",
                    a.box(
                        f"HandguardVent{nm}{i}",
                        (r * self.L * 0.8, r * self.L * 0.5, (u1 - u0) * self.L * 0.1),
                        (s * r * self.L, y, -self.U(uc)),
                        self.m["trim"],
                        bevel=0,
                    ),
                )
        self._rail(u0 + 0.01, u1 - 0.01, name="HandguardRail", h=r + 0.0)

    def _handguard_pump(self):
        a, k = self.a, self.k
        u0, u1 = k["handguard"]
        y = self.V(-0.032)
        r = 0.03 * self.L * self.chunk
        z0, z1 = -self.U(u0), -self.U(u1)
        stations = []
        n = 7
        for i in range(n + 1):
            z = z0 + (z1 - z0) * i / n
            rr = r * (0.92 if i % 2 else 1.0) if 0 < i < n else r * 0.85
            stations.append((z, rr, rr * 0.85, (0, y)))
        a.loft("Handguard", stations, self.m["furniture"] if self.style == "military" else self.m["polymer"], axis="Z", segments=14)

    # ---------------------------------------------------------------- railgun (one armoured body)
    def _railgun(self):
        """A long boxy energy rifle built region by region against the 'Reaper XV 331' reference: a tall skeleton
        stock that closes under a vertical ribbed grip, a charcoal receiver with maker text + ring light + charging
        slot, three slotted U-strap clamps, a long front shroud with a sectioned slate panel, a continuous fin rail
        on a raised spine, a body-height glossy drum, and a chamfered nose with vertical light slits."""
        a, k, p = self.a, self.k, self.parts
        m = dict(self.m)
        m.setdefault("decal", m["trim"])
        gloss = m.get("gloss", m["steel"])
        W = self.w(k["width"])
        top, bot = 0.062, -0.056
        front_top = 0.05  # the front shroud is lower than the receiver (the step hides under the clamps)
        sb = -0.145  # the frame bottom: the skeleton stock closes under the grip
        self.front_top, self.frame_bottom = front_top, sb
        body = [
            (0.005, sb, 0.008),
            (0.005, 0.09, 0.01),
            (0.03, 0.097, 0.006),
            (0.2, 0.104, 0.004),
            (0.25, top, 0.004),
            (0.3, top),
            (0.565, top),
            (0.575, front_top),
            (0.925, front_top, 0.003),
            (0.95, 0.04),
            (0.97, 0.036, 0.002),
            (0.99, 0.016, 0.002),
            (0.99, -0.03, 0.002),
            (0.975, -0.042, 0.002),
            (0.955, bot, 0.003),
            (0.47, bot),
            (0.45, bot + 0.006),
            (0.255, bot + 0.006),
            (0.255, sb + 0.02, 0.006),
            (0.24, sb, 0.006),
        ]
        a.extrude("Body", self.outline(body), W, m["frame"], bevel=0.016)
        # skeleton stock: one large rectangular hole in the lower half (rear strut, bottom bar, front post around it)
        a.cut("Body", a.extrude("StockHole", self.outline([(0.045, -0.12, 0.008), (0.215, -0.12, 0.008), (0.215, -0.03, 0.008), (0.045, -0.03, 0.008)]), W * 1.4, m["trim"], bevel=0))
        for sd, nm in ((1, "R"), (-1, "L")):
            x = sd * W / 2
            for i, (u0, u1, h) in enumerate(((0.3, 0.93, 0.02), (0.48, 0.94, -0.022), (0.04, 0.2, 0.054))):
                a.cut("Body", a.box(f"Groove{nm}{i}", (self.w(0.014), 0.0045 * self.L, self.zs(u0, u1)), (x, self.V(h), -(self.U(u0) + self.U(u1)) / 2), m["trim"], bevel=0))
            a.cut("Body", a.box(f"GrooveV{nm}", (self.w(0.01), (top - bot) * self.L * 0.7, 0.003 * self.L), (x, self.V(0.004), -self.U(0.465)), m["trim"], bevel=0))
            # the long front slate panel + a slate patch on the stock's front corner
            for i, pts in enumerate((
                [(0.585, -0.034), (0.89, -0.034), (0.915, -0.016), (0.89, -0.002), (0.62, -0.002), (0.585, -0.012)],
                [(0.19, 0.035), (0.225, 0.03), (0.225, 0.052), (0.2, 0.058)],
            )):
                a.extrude(f"Panel{nm}{i}", self.outline(pts), self.w(0.006), m["furniture"], pos=(x + sd * self.w(0.002), 0, 0), bevel=0.004)
            # ring light + its dark core (below the maker text, near the front of the receiver)
            a.cylinder(f"RingLight{nm}", 0.019 * self.L, self.w(0.006), (x + sd * self.w(0.002), self.V(0.004), -self.U(0.42)), m["glow"], axis="X", segments=24, bevel=0)
            a.cylinder(f"RingCore{nm}", 0.0145 * self.L, self.w(0.009), (x + sd * self.w(0.003), self.V(0.004), -self.U(0.42)), m["trim"], axis="X", segments=24, bevel=0)
            # two thin VERTICAL light slits behind the muzzle
            for j, uu in enumerate((0.952, 0.964)):
                a.box(f"NoseSlit{nm}{j}", (self.w(0.006), 0.026 * self.L, self.zs(uu - 0.0018, uu + 0.0018)), (x + sd * self.w(0.002), self.V(-0.006), -self.U(uu)), m["glow"], bevel=0)
            # short orange accents along the receiver's lower edge
            for j, uu in enumerate((0.34, 0.46)):
                a.box(f"MidSlit{nm}{j}", (self.w(0.006), 0.004 * self.L, 0.02 * self.L), (x + sd * self.w(0.002), self.V(-0.04), -self.U(uu)), m["glow"], bevel=0)
            # barcode under the serial (right of the ring light as the reference is seen)
            for j in range(7):
                a.box(f"Code{nm}{j}", (self.w(0.004), 0.007 * self.L, (0.0012 + (j % 3) * 0.0008) * self.L), (x + sd * self.w(0.002), self.V(-0.009), -self.U(0.36 + j * 0.0045)), m["decal"], bevel=0)
            a.box(f"StockLight{nm}", (self.w(0.006), 0.035 * self.L, 0.004 * self.L), (x + sd * self.w(0.002), self.V(-0.005), -self.U(0.03)), m["glow"], bevel=0)
        # the fin rail: a raised spine along the top, carrying one continuous row of identical fins over the clamps
        fin_l, gap = 0.0042, 0.0042
        fin_h = 0.009
        spine = 0.011

        def top_line(u):
            # the body's top edge (matches the outline: 0.035 -> 0.1, 0.2 -> 0.076, 0.3 -> top)
            if u >= 0.575:
                return front_top
            if u >= 0.25:
                return top
            if u >= 0.2:
                return 0.104 + (top - 0.104) * (u - 0.2) / 0.05
            if u >= 0.03:
                return 0.097 + (0.104 - 0.097) * (u - 0.03) / 0.17
            return 0.09 + (0.097 - 0.09) * (u - 0.005) / 0.025

        self.top_line = top_line
        for nm_, (u0, u1, h0) in (("SpineRear", (0.296, 0.577, top)), ("SpineFront", (0.573, 0.905, front_top))):
            a.box(nm_, (W * 0.55, (spine + 0.003) * self.L, self.zs(u0, u1)), (0, self.V(h0 - 0.003 + (spine + 0.003) / 2), -(self.U(u0) + self.U(u1)) / 2), m["frame"], bevel=0.004)
        r0, r1 = 0.302, 0.896
        count = int((r1 - r0 + gap) / (fin_l + gap))
        start = r0 + (r1 - r0 - (count * fin_l + (count - 1) * gap)) / 2 + fin_l / 2
        for i in range(count):
            u = start + i * (fin_l + gap)
            h = top_line(u) + spine
            # tiny repeated detail: no bevel (a beveled fin costs ~100 tris)
            a.box(f"Fin{i}", (W * 0.5, fin_h * self.L, fin_l * self.L), (0, self.V(h - 0.002 + fin_h / 2), -self.U(u)), m["trim"], bevel=0)
        a.box("RidgePost", (W * 0.56, (fin_h + 0.006) * self.L, self.zs(0.898, 0.91)), (0, self.V(front_top + spine - 0.002 + (fin_h + 0.006) / 2), -self.U(0.904)), m["trim"], bevel=0.004)
        a.box("RidgeNotch", (W * 0.56, (fin_h + 0.002) * self.L, 0.016 * self.L), (0, self.V(top + spine - 0.002 + (fin_h + 0.002) / 2), -self.U(0.296)), m["trim"], bevel=0.004)
        a.cut("RidgeNotch", a.box("RidgeNotchCut", (W * 0.24, 0.008 * self.L, 0.03 * self.L), (0, self.V(top + spine + fin_h), -self.U(0.296)), m["trim"], bevel=0))
        # three U-strap clamps over a slate channel, seated in a shallow recess; each has a vertical slot in its side
        for sd in (1, -1):
            a.cut("Body", a.box(f"CollarSeat{sd}", (self.w(0.008), (top - bot) * self.L * 0.78, self.zs(0.493, 0.587)), (sd * W / 2, self.V((top + bot) / 2), -(self.U(0.493) + self.U(0.587)) / 2), m["trim"], bevel=0))
        # three SEPARATE straps with strap-wide gaps: the slate channel shows between them
        for i, (u0, u1) in enumerate(((0.498, 0.511), (0.534, 0.547), (0.57, 0.583))):
            # each strap rises above the body (below the fin tops) and wraps down past the bottom edge
            a.box(f"Clamp{i}", (W * 1.2, (top - bot + 0.014) * self.L, self.zs(u0, u1)), (0, self.V((top + bot) / 2), -(self.U(u0) + self.U(u1)) / 2), m["trim"], bevel=0.004)
            for sd in (1, -1):
                # the window goes THROUGH the strap's side wall: the slate channel shows behind it (the reference)
                a.cut(f"Clamp{i}", a.box(f"ClampSlot{i}{sd}", (W * 0.2, (top - bot) * 0.6 * self.L, self.zs(u0, u1) * 0.5), (sd * W * 0.58, self.V((top + bot) / 2 + 0.006), -(self.U(u0) + self.U(u1)) / 2), m["trim"], bevel=0))
        # the barrel: a ringed round muzzle from the lower half of the nose
        nose = self.U(0.99)
        self.muzzle_h = -0.017
        self.muzzle_at = nose + 0.082 * self.L
        mz = lambda d: (0, self.V(-0.017), -(nose + d * self.L))  # noqa: E731
        a.cylinder("Muzzle", 0.0092 * self.L, 0.042 * self.L, mz(0.019), gloss, axis="Z", segments=16, bevel=0.005)
        a.cylinder("MuzzleStep", 0.0068 * self.L, 0.04 * self.L, mz(0.058), gloss, axis="Z", segments=16, bevel=0.003)
        a.cylinder("MuzzleRing", 0.0118 * self.L, 0.008 * self.L, mz(0.006), m["trim"], axis="Z", segments=16, bevel=0.003)
        for j, d in enumerate((0.018, 0.028)):
            a.cylinder(f"MuzzleGroove{j}", 0.0099 * self.L, 0.003 * self.L, mz(d), m["trim"], axis="Z", segments=16, bevel=0)
        a.cylinder("MuzzleCollar", 0.01 * self.L, 0.006 * self.L, mz(0.04), m["trim"], axis="Z", segments=16, bevel=0.003)
        a.cylinder("MuzzleTip", 0.0082 * self.L, 0.006 * self.L, mz(0.077), m["trim"], axis="Z", segments=16, bevel=0.003)
        a.cylinder("MuzzleCore", 0.0038 * self.L, 0.004 * self.L, mz(0.081), m["glow"], axis="Z", segments=12, bevel=0)
        # a straight, near-vertical blocky grip with horizontal ribs; the frame's bottom bar runs into its foot
        rake = math.radians(k["grip_rake"])
        gu, gt, gl = k["grip_u"], bot + 0.006, k["grip_len"]
        du, dh = -math.sin(rake) * gl, -math.cos(rake) * gl
        gw = self.w(0.04)
        a.extrude("Grip", self.outline([(gu - 0.02, gt + 0.004), (gu + 0.022, gt + 0.004), (gu + 0.022 + du, gt + dh, 0.004), (gu - 0.02 + du, gt + dh, 0.004)]), gw, m["frame"], bevel=0.008)
        for j in range(6):
            hh = gt - 0.022 - j * 0.0115
            uu = gu + du * (gt - hh) / max(-dh, 1e-6)
            for sd in (1, -1):
                a.cut("Grip", a.box(f"GripRib{j}{sd}", (self.w(0.006), 0.004 * self.L, 0.06 * self.L), (sd * gw / 2, self.V(hh), -self.U(uu)), m["trim"], bevel=0))
        a.extrude("TriggerGuard", self.outline([(gu + 0.025, gt), (gu + 0.025, gt - 0.03, 0.002), (gu + 0.07, gt - 0.03, 0.002), (gu + 0.078, gt)]), self.w(0.012), m["trim"], bevel=0.003)
        a.cut("TriggerGuard", a.extrude("GuardHole", self.outline([(gu + 0.031, gt - 0.002), (gu + 0.031, gt - 0.024, 0.002), (gu + 0.064, gt - 0.024, 0.002), (gu + 0.07, gt - 0.002)]), self.w(0.03), m["trim"], bevel=0))
        a.extrude("Trigger", self.outline([(gu + 0.042, gt), (gu + 0.05, gt), (gu + 0.047, gt - 0.02, 0.004), (gu + 0.04, gt - 0.012)]), self.w(0.008), m["steel"], bevel=0.002)
        # charging slot on both sides; the handle on the LEFT (the side the reference shows), at the slot's rear end
        lever_u = 0.305
        for sd, nm in ((1, "R"), (-1, "L")):
            import rbx_parts as P

            # ~40% of the receiver: a long, dark, clearly recessed slot
            P.inset_panel(a, "Body", f"ChargeSlot{nm}", self.outline([(0.296, 0.016), (0.46, 0.016), (0.466, 0.0235), (0.46, 0.031), (0.296, 0.031)]), m["steel"], surface=sd * W / 2, side=sd, depth=0.016, chamfer=0.002)
        # the handle: from the slot's rear end, angled back and out, with a knob
        a.box("ChargeLever", (self.w(0.05), 0.008 * self.L, 0.012 * self.L), (-W / 2 - self.w(0.02), self.V(0.0235), -self.U(lever_u) + 0.02), m["steel"], rot=(0, 25, 0), bevel=0.003)
        a.cylinder("ChargeKnob", 0.009 * self.L, 0.016 * self.L, (-W / 2 - self.w(0.042), self.V(0.0235), -self.U(lever_u) + 0.065), m["trim"], axis="Z", segments=12, bevel=0.003)
        a.anchor("Bolt", (-W / 2 - self.w(0.042), self.V(0.0235), -self.U(lever_u) + 0.065))
        # the drum: a body-height glossy cylinder along the barrel, under the receiver just ahead of the grip,
        # flat end caps, a few raised rings near its FRONT end
        u0, u1, _ = k["mag"]
        r = 0.043 * self.L  # long and slim: ~1.7x as long as it is thick (a short fat drum reads as a disc)
        mh = bot - 0.004 - r / self.L
        self.drum = (u0, u1, mh, r)
        a.box("DrumMount", (self.w(0.04), 0.04 * self.L, (u1 - u0) * self.L * 0.7), (0, self.V(bot - 0.012), -self.U((u0 + u1) / 2)), m["trim"], bevel=0.006)
        drum_m = m.get("polished", gloss)
        a.cylinder("Drum", r, (u1 - u0) * self.L, (0, self.V(mh), -self.U((u0 + u1) / 2)), drum_m, axis="Z", segments=32, bevel=0.012)
        for i, uu in enumerate((u0 + 0.0005, u1 - 0.0005)):
            # each cap is centred near the end face so it stands proud of it (never coplanar with it)
            a.cylinder(f"DrumCap{i}", r * 1.03, 0.008 * self.L, (0, self.V(mh), -self.U(uu)), drum_m, axis="Z", segments=32, bevel=0.003)
        a.cylinder("DrumFace", r * 0.7, 0.004 * self.L, (0, self.V(mh), -self.U(u1) - 0.005 * self.L), drum_m, axis="Z", segments=32, bevel=0.0015)
        for j, uu in enumerate((u1 - 0.016, u1 - 0.026, u1 - 0.036)):
            a.cylinder(f"DrumRing{j}", r * 1.022, 0.004 * self.L, (0, self.V(mh), -self.U(uu)), drum_m, axis="Z", segments=32, bevel=0.0015)
        # optic on the rail
        self.rail_top = top + spine - 0.002 + fin_h  # the real top of the fin rail over the receiver
        if p["optic"] != "none":
            getattr(self, f"_optic_{p['optic']}")()
        self._railgun_detail(W, top, bot)
        return self

    def _railgun_detail(self, W, top, bot):
        """Secondary + tertiary forms per region: stock armour/ribs/vents, receiver markings + panel lines, clamp
        channel + screws, front panel sections + light channel + chevrons + lower step plate, nose insert, pads."""
        import rbx_parts as P

        a = self.a
        m = dict(self.m)
        m.setdefault("decal", m["trim"])
        L = self.L
        sb = self.frame_bottom
        for sd, nm in ((1, "R"), (-1, "L")):
            x = sd * W / 2
            face = "+X" if sd > 0 else "-X"
            # ---- stock: ribbed rear strut, angled slate armour, a narrower slate panel toward the butt
            P.plate(a, f"StockPlate{nm}", self.outline([(0.02, sb + 0.012), (0.04, sb + 0.008), (0.04, 0.05), (0.02, 0.055)]), m["frame"], surface=x, side=sd, thickness=0.012, chamfer=0.005)
            for j in range(7):
                hh = -0.112 + j * 0.0125
                P.inset_panel(a, f"StockPlate{nm}", f"StockRib{nm}{j}", self.outline([(0.022, hh), (0.038, hh), (0.038, hh + 0.004), (0.022, hh + 0.004)]), m["trim"], surface=x + sd * 0.012, side=sd, depth=0.005, chamfer=0.001)
            for j in range(3):
                P.inset_panel(a, f"StockPlate{nm}", f"StrutVent{nm}{j}", self.outline([(0.024, 0.02 + j * 0.009), (0.036, 0.02 + j * 0.009), (0.036, 0.025 + j * 0.009), (0.024, 0.025 + j * 0.009)]), m["trim"], surface=x + sd * 0.012, side=sd, depth=0.006, chamfer=0.0015)
            P.inset_panel(a, "Body", f"StockArmour{nm}", self.outline([(0.13, -0.018), (0.2, -0.018), (0.212, 0.0), (0.2, 0.046), (0.15, 0.046)]), m["furniture"], surface=x, side=sd, depth=0.01, chamfer=0.003)
            P.inset_panel(a, "Body", f"StockRear{nm}", self.outline([(0.07, -0.016), (0.1, -0.016), (0.1, 0.044), (0.07, 0.05)]), m["furniture"], surface=x, side=sd, depth=0.01, chamfer=0.003)
            with a.floaters():
                P.screws(a, f"StockScrew{nm}", [(x, self.V(hh), -self.U(uu)) for uu, hh in ((0.12, -0.022), (0.22, -0.022), (0.12, 0.05), (0.215, 0.05))], m["steel"], facing=face, radius=0.014)
            P.stripes(a, f"Chevron{nm}", (self.U(0.196), self.V(0.06)), (0.014 * L, 0.009 * L), (m["glow"], m["decal"]), surface=x, side=sd, count=2, slant=0.7, thickness=0.004)
            # bottom bar: a recessed panel held by two screws
            P.inset_panel(a, "Body", f"StockBarInset{nm}", self.outline([(0.06, sb + 0.006), (0.19, sb + 0.006), (0.2, sb + 0.0125), (0.19, sb + 0.019), (0.06, sb + 0.019)]), m["trim"], surface=x, side=sd, depth=0.006, chamfer=0.002)
            with a.floaters():
                P.screws(a, f"StockBarScrew{nm}", [(x + sd * 0.001, self.V(sb + 0.0125), -self.U(uu)) for uu in (0.075, 0.175)], m["steel"], facing=face, radius=0.011)
            # ---- receiver: charcoal, angled panel lines, latch, LED, maker text + model number in the reference's
            # reading order (muzzle-to-stock on the left side), serial under... the slot, a label plate
            P.inset_panel(a, "Body", f"RecInset{nm}", self.outline([(0.24, -0.03), (0.285, -0.03), (0.295, -0.012), (0.295, 0.012), (0.25, 0.012)]), m["trim"], surface=x, side=sd, depth=0.01, chamfer=0.004)
            P.latch(a, f"Latch{nm}", (x, self.V(-0.012), -self.U(0.27)), m["steel"], facing=face, size=(0.08, 0.12))
            P.led(a, f"Led{nm}", (x, self.V(0.03), -self.U(0.258)), m["glow"], m["trim"], facing=face, radius=0.014)
            # "Reaper" + a small "INDUSTRIES" + "XV 331", read muzzle-to-stock on the left (the reference's side)
            reaper_u, ind_u, model_u = (0.445, 0.399, 0.345) if sd < 0 else (0.322, 0.368, 0.43)
            a.text(f"MakerText{nm}", "Reaper", (x, self.V(0.0545), -self.U(reaper_u)), m["decal"], size=0.06, facing=face, up="+Y", depth=0.01)
            a.text(f"MakerSub{nm}", "INDUSTRIES", (x, self.V(0.0525), -self.U(ind_u)), m["decal"], size=0.03, facing=face, up="+Y", depth=0.008)
            a.text(f"ModelText{nm}", "XV 331", (x, self.V(0.0535), -self.U(model_u)), m["decal"], size=0.075, facing=face, up="+Y", depth=0.01)
            a.text(f"SerialText{nm}", "29178-398", (x, self.V(0.002), -self.U(0.373)), m["decal"], size=0.04, facing=face, up="+Y", depth=0.008)
            P.groove(a, "Body", f"RecLines{nm}", self.outline([(0.3, -0.04), (0.318, -0.026), (0.395, -0.026), (0.405, -0.034)]), m["trim"], surface=x, side=sd, width=0.01, depth=0.007)
            # a small square stamped label plate under the slot's rear end (bare metal so it reads)
            P.plate(a, f"LabelPlate{nm}", self.outline([(0.298, -0.012), (0.318, -0.012), (0.318, 0.01), (0.298, 0.01)]), m["steel"], surface=x, side=sd, thickness=0.006, chamfer=0.002)
            for j in range(3):
                a.box(f"LabelLine{nm}{j}", (self.w(0.003), 0.0016 * self.L, 0.012 * self.L), (x + sd * 0.006, self.V(0.004 - j * 0.005), -self.U(0.308)), m["decal"], bevel=0)
            # ---- clamps: the slate channel visible between the straps, a screw low on each strap
            P.plate(a, f"ClampChannel{nm}", self.outline([(0.495, -0.03), (0.585, -0.03), (0.585, 0.03), (0.495, 0.03)]), m["furniture"], surface=x - sd * self.w(0.004), side=sd, thickness=0.012, chamfer=0.003)
            with a.floaters():
                P.screws(a, f"ClampScrew{nm}", [(sd * W * 0.6, self.V(-0.046), -self.U(uu)) for uu in (0.5045, 0.5405, 0.5765)], m["steel"], facing=face, radius=0.009)
            # ---- front side: the slate panel's diagonal sections, chevrons in the upper plate, a light channel
            # above the panel near its front end, a full-length stepped lower plate
            P.plate(a, f"PanelBase{nm}", self.outline([(0.578, -0.039), (0.894, -0.039), (0.922, -0.016), (0.894, 0.003), (0.614, 0.003), (0.578, -0.014)]), m["trim"], surface=x, side=sd, thickness=self.w(0.003), chamfer=0.004)
            for j, uu in enumerate((0.66, 0.72, 0.78, 0.84)):
                P.inset_panel(a, f"Panel{nm}0", f"Diag{nm}{j}", self.outline([(uu, -0.033), (uu + 0.007, -0.033), (uu + 0.02, -0.003), (uu + 0.013, -0.003)]), m["trim"], surface=x + sd * (self.w(0.002) + self.w(0.006) / 2), side=sd, depth=0.008, chamfer=0.002)
            for j in range(6):
                vu = 0.62 + j * 0.022
                P.inset_panel(a, "Body", f"FrontVent{nm}{j}", self.outline([(vu, 0.008), (vu + 0.012, 0.008), (vu + 0.012, 0.015), (vu, 0.015)]), m["trim"], surface=x, side=sd, depth=0.008, chamfer=0.002)
            P.inset_panel(a, "Body", f"LightChannel{nm}", self.outline([(0.8, 0.0065), (0.9, 0.0065), (0.9, 0.0145), (0.8, 0.0145)]), m["trim"], surface=x, side=sd, depth=0.009, chamfer=0.002)
            a.box(f"ChannelLight{nm}", (self.w(0.004), 0.005 * L, self.zs(0.86, 0.885)), (x - sd * self.w(0.0015), self.V(0.0105), -self.U(0.8725)), m["glow"], bevel=0)
            P.plate(a, f"FrontPlate{nm}", self.outline([(0.6, 0.022), (0.86, 0.022), (0.875, 0.035), (0.86, 0.043), (0.62, 0.043)]), m["frame"], surface=x, side=sd, thickness=0.01, chamfer=0.005)
            for j, uu in enumerate((0.69, 0.75, 0.81)):
                P.inset_panel(a, f"FrontPlate{nm}", f"Chev{nm}{j}", self.outline([(uu, 0.026), (uu + 0.008, 0.026), (uu + 0.018, 0.0325), (uu + 0.008, 0.039), (uu, 0.039), (uu + 0.01, 0.0325)]), m["trim"], surface=x + sd * 0.01, side=sd, depth=0.005, chamfer=0.001)
            with a.floaters():
                P.screws(a, f"FrontScrew{nm}", [(x + sd * 0.01, self.V(0.033), -self.U(uu)) for uu in (0.615, 0.855)], m["steel"], facing=face, radius=0.014)
            P.plate(a, f"LowPlate{nm}", self.outline([(0.585, -0.054), (0.93, -0.054), (0.93, -0.044), (0.592, -0.044)]), m["frame"], surface=x, side=sd, thickness=self.w(0.004), chamfer=0.003)
            # ---- nose: a small slate insert just behind the light slits
            P.plate(a, f"NoseInsert{nm}", self.outline([(0.928, -0.03), (0.944, -0.03), (0.944, 0.004), (0.928, 0.004)]), m["furniture"], surface=x, side=sd, thickness=0.008, chamfer=0.003)
        # ---- an orange outlined rectangle on the stock top near the butt
        tl = self.top_line
        for j, (uu, xx, lu, lx) in enumerate(((0.05, 0, 0.003, W * 0.5), (0.095, 0, 0.003, W * 0.5), (0.0725, W * 0.25, 0.048, W * 0.035), (0.0725, -W * 0.25, 0.048, W * 0.035))):
            a.box(f"StockMark{j}", (lx, 0.003 * L, lu * L), (xx, self.V(tl(uu)) + 0.0006 * L, -self.U(uu)), m["glow"], bevel=0)
        # ---- the rubber butt pad with a seam, the sling mount under the bottom bar, an accessory rail, a sensor
        a.extrude("ButtPad", self.outline([(-0.014, sb + 0.006, 0.006), (0.009, sb + 0.003), (0.009, 0.08), (-0.014, 0.076, 0.006)]), W * 1.06, m["rubber"], bevel=0.006)
        for sd, nm in ((1, "R"), (-1, "L")):
            P.groove(a, "ButtPad", f"ButtSeam{nm}", self.outline([(-0.004, sb + 0.012), (-0.004, 0.072)]), m["trim"], surface=sd * W * 0.53, side=sd, width=0.006, depth=0.006)
        a.box("SlingMount", (W * 0.3, 0.012 * L, 0.03 * L), (0, self.V(sb) - 0.004 * L, -self.U(0.1)), m["steel"], bevel=0.004)
        a.cylinder("SlingLoop", 0.01 * L, W * 0.5, (0, self.V(sb) - 0.012 * L, -self.U(0.1)), m["steel"], axis="X", segments=10, bevel=0.003)
        a.box("UnderRail", (W * 0.45, 0.01 * L, self.zs(0.72, 0.88)), (0, self.V(bot) - 0.005 * L, -self.U(0.8)), m["trim"], bevel=0)
        for j in range(8):
            a.box(f"UnderRailTooth{j}", (W * 0.5, 0.006 * L, 0.008 * L), (0, self.V(bot) - 0.011 * L, -self.U(0.73 + j * 0.02)), m["trim"], bevel=0)
        a.box("NoseSensor", (W * 0.5, 0.012 * L, 0.04 * L), (0, self.V(bot - 0.004), -self.U(0.93)), m["trim"], bevel=0.006)
        a.cylinder("NoseLens", 0.004 * L, 0.004 * L, (0, self.V(bot - 0.004), -self.U(0.952)), m["glow"], axis="Z", segments=10, bevel=0)

    # ---------------------------------------------------------------- sci-fi parts
    def _muzzle_emitter(self):
        """Energy emitter: a collar, three forward prongs and a glowing core (reads 'not a bullet gun')."""
        a, k = self.a, self.k
        u1 = k["barrel_end"]
        length = 0.07
        self.muzzle_u = u1 + length
        r = k["barrel_r"][1] * self.L * self.chunk
        y = self.V(0)
        a.cylinder("Muzzle", r * 2.2, length * self.L * 0.35, (0, y, -self.U(u1 + length * 0.15)), self.m["trim"], axis="Z", segments=16)
        a.cylinder("MuzzleCore", r * 1.1, length * self.L * 0.8, (0, y, -self.U(u1 + length * 0.5)), self.m["glow"], axis="Z", segments=12, bevel=0)
        for i, ang in enumerate((90, 210, 330)):
            rad = math.radians(ang)
            x, yy = math.cos(rad) * r * 2.0, math.sin(rad) * r * 2.0
            a.box(f"MuzzleProng{i}", (r * 0.8, r * 0.8, length * self.L * 0.9), (x, y + yy, -self.U(u1 + length * 0.55)), self.m["frame"], rot=(0, 0, ang), bevel=0.01)

    def _handguard_shroud(self):
        """Angular armoured shroud over the barrel: chamfered side profile, slanted vents, a glow slit each side."""
        a, k = self.a, self.k
        u0, u1 = k["handguard"]
        top, bot = 0.03, -0.04
        a.extrude(
            "Handguard",
            self.outline([(u0, top - 0.004), (u0 + 0.03, top), (u1 - 0.06, top, 0.004), (u1, top - 0.018), (u1, bot + 0.016), (u1 - 0.04, bot), (u0 + 0.05, bot, 0.006), (u0, bot + 0.012)]),
            self.w(k["width"] * 1.25),
            self.m["frame"],
            bevel=0.012,
        )
        a.cut(
            "Handguard",
            a.cylinder("BarrelChannel", k["barrel_r"][0] * self.L * self.chunk * 1.3, (u1 - u0) * self.L + 0.2, (0, self.V(0), -self.U((u0 + u1) / 2)), self.m["trim"], axis="Z", segments=14, bevel=0),
        )
        for i in range(4):
            uc = u0 + (u1 - u0) * (0.2 + i * 0.17)
            a.cut(
                "Handguard",
                a.box(f"ShroudVent{i}", (self.w(k["width"] * 1.6), 0.004 * self.L * 2.2, (u1 - u0) * self.L * 0.06), (0, self.V(top - 0.006), -self.U(uc)), self.m["trim"], rot=(-25, 0, 0), bevel=0),
            )
        for s_, nm in ((1, "R"), (-1, "L")):
            a.box(
                f"ShroudSlit{nm}",
                (self.w(0.004), 0.006 * self.L, (u1 - u0) * self.L * 0.7),
                (s_ * self.w(k["width"] * 1.25) / 2, self.V(-0.012), -self.U((u0 + u1) / 2)),
                self.m["glow"],
                bevel=0,
            )

    def _optic_digital(self):
        """Digital sight: an angular housing, a big glowing front lens, a rear display, a sensor stub."""
        a, k = self.a, self.k
        oh = k["optic_h"]
        self.sight_h = oh
        ru, rf = k["receiver"][0] + 0.01, k["receiver"][1] + 0.06
        rail = getattr(self, "rail_top", k["receiver_h"][1])
        hh = 0.024  # half height of the housing (fraction of L)
        a.extrude(
            "Optic",
            self.outline([(ru, oh - hh), (rf - 0.02, oh - hh), (rf, oh - hh * 0.4), (rf, oh + hh * 1.1, 0.006), (rf - 0.05, oh + hh * 1.35), (ru + 0.03, oh + hh * 1.35, 0.01), (ru, oh + hh * 0.8)]),
            self.w(0.05),
            self.m["frame"],
            bevel=0.012,
        )
        a.box("OpticLens", (self.w(0.042), hh * 1.9 * self.L, 0.012), (0, self.V(oh + hh * 0.3), -self.U(rf + 0.001)), self.m["glass"], group="glass", bevel=0)
        a.box("OpticScreen", (self.w(0.036), hh * 1.4 * self.L, 0.012), (0, self.V(oh + hh * 0.3), -self.U(ru - 0.001)), self.m["glow"], bevel=0)
        a.cylinder("OpticSensor", 0.006 * self.L, 0.05 * self.L, (self.w(0.032), self.V(oh + hh), -self.U(rf - 0.04)), self.m["trim"], axis="Z", segments=10)
        for i, uu in enumerate((ru + 0.04, rf - 0.06)):
            ring_bottom = self.V(oh - hh)
            base_top = self.V(rail)
            a.box(f"OpticMount{i}", (self.w(0.034), max(0.02, ring_bottom - base_top + 0.01), 0.02 * self.L), (0, (ring_bottom + base_top) / 2, -self.U(uu)), self.m["trim"], bevel=0.006)

    def _stock_thumbhole(self):
        a, k = self.a, self.k
        s0, s1 = k["stock"]
        bh0, bh1 = k["butt_h"]
        r0h = k["receiver_h"]
        g_rear = k["grip_u"] - 0.03
        a.extrude(
            "Stock",
            self.outline(
                [
                    (s1 + 0.005, r0h[1] - 0.004),
                    (s0 + 0.06, bh1 - 0.006, 0.02),
                    (s0 + 0.012, bh1, 0.01),
                    (s0 + 0.012, bh0, 0.012),
                    (s0 + 0.06, bh0, 0.025),
                    (g_rear - 0.13, r0h[0] - 0.052, 0.03),
                    (g_rear - 0.06, r0h[0] - 0.088, 0.03),
                    (g_rear + 0.005, r0h[0] - 0.098),
                    (g_rear + 0.02, r0h[0] - 0.02),
                    (s1 + 0.005, r0h[0] + 0.004),
                ]
            ),
            self.w(0.04),
            self.m["furniture"] if self.style == "military" else self.m["polymer"],
            bevel=0.016,
        )
        # skeleton: the thumbhole behind the grip + a lightening window in the butt (precision-stock read)
        a.cut(
            "Stock",
            a.extrude(
                "Thumbhole",
                self.outline([(g_rear - 0.1, r0h[0] - 0.006, 0.02), (g_rear - 0.012, r0h[0] - 0.006, 0.016), (g_rear - 0.012, r0h[0] - 0.078, 0.02), (g_rear - 0.06, r0h[0] - 0.07, 0.02), (g_rear - 0.105, r0h[0] - 0.045, 0.02)]),
                self.w(0.06),
                self.m["trim"],
                bevel=0,
            ),
        )
        a.cut(
            "Stock",
            a.extrude(
                "StockWindow",
                self.outline([(s0 + 0.045, bh1 - 0.028, 0.02), (s0 + 0.17, r0h[0] + 0.006, 0.022), (s0 + 0.15, r0h[0] - 0.035, 0.02), (s0 + 0.045, bh0 + 0.03, 0.02)]),
                self.w(0.06),
                self.m["trim"],
                bevel=0,
            ),
        )
        # cheek riser + rubber buttpad
        a.extrude(
            "CheekRiser",
            self.outline([(s0 + 0.12, bh1 - 0.004), (s0 + 0.26, r0h[1] - 0.004, 0.006), (s0 + 0.26, r0h[1] + 0.014, 0.008), (s0 + 0.13, bh1 + 0.016, 0.008)]),
            self.w(0.034),
            self.m["polymer"],
            bevel=0.01,
        )
        a.extrude(
            "Buttpad",
            self.outline([(s0, bh1 - 0.004, 0.006), (s0 + 0.014, bh1 - 0.002), (s0 + 0.014, bh0 + 0.002), (s0, bh0 + 0.004, 0.006)]),
            self.w(0.044),
            self.m["rubber"],
            bevel=0.01,
        )

    def _stock_solid(self):
        a, k = self.a, self.k
        s0, s1 = k["stock"]
        bh0, bh1 = k["butt_h"]
        r0h = k["receiver_h"]
        a.extrude(
            "Stock",
            self.outline(
                [
                    (s1 + 0.005, r0h[1] - 0.008),
                    (s1 - 0.06, r0h[1] - 0.016, 0.03),
                    (s0 + 0.05, bh1 - 0.004, 0.03),
                    (s0 + 0.012, bh1, 0.01),
                    (s0 + 0.012, bh0, 0.012),
                    (s0 + 0.06, bh0 + 0.006, 0.04),
                    (k["grip_u"] - 0.06, r0h[0] - 0.032, 0.03),
                    (s1 + 0.005, r0h[0] + 0.004),
                ]
            ),
            self.w(0.042),
            self.m["furniture"] if self.style == "military" else self.m["polymer"],
            bevel=0.016,
        )
        a.extrude(
            "Buttpad",
            self.outline([(s0, bh1 - 0.004, 0.006), (s0 + 0.014, bh1 - 0.002), (s0 + 0.014, bh0 + 0.002), (s0, bh0 + 0.004, 0.006)]),
            self.w(0.046),
            self.m["rubber"],
            bevel=0.01,
        )

    def _stock_collapsible(self):
        a, k = self.a, self.k
        s0, s1 = k["stock"]
        bh0, bh1 = k["butt_h"]
        r = 0.017 * self.L * self.chunk
        a.cylinder("BufferTube", r, (s1 - s0 - 0.04) * self.L, (0, self.V(0.004), -self.U((s0 + 0.04 + s1) / 2)), self.m["trim"], axis="Z", segments=14)
        a.extrude(
            "Stock",
            self.outline(
                [
                    (s0, bh1, 0.008),
                    (s0 + 0.17, bh1 - 0.008, 0.01),
                    (s0 + 0.18, -0.022, 0.008),
                    (s0 + 0.10, -0.03),
                    (s0 + 0.06, bh0 + 0.01, 0.015),
                    (s0, bh0, 0.008),
                ]
            ),
            self.w(0.042),
            self.m["polymer"],
            bevel=0.012,
        )
        a.cut(
            "Stock",
            a.extrude(
                "StockHole",
                self.outline([(s0 + 0.035, -0.025, 0.008), (s0 + 0.09, -0.028, 0.008), (s0 + 0.05, bh0 + 0.035, 0.012), (s0 + 0.03, bh0 + 0.04, 0.008)]),
                self.w(0.06),
                self.m["trim"],
                bevel=0,
            ),
        )
        a.extrude(
            "Buttpad",
            self.outline([(s0 - 0.008, bh1 - 0.002, 0.004), (s0 + 0.004, bh1), (s0 + 0.004, bh0), (s0 - 0.008, bh0 + 0.004, 0.004)]),
            self.w(0.046),
            self.m["rubber"],
            bevel=0.008,
        )

    def _stock_folding(self):
        a, k = self.a, self.k
        s0, s1 = k["stock"]
        bh0, bh1 = k["butt_h"]
        t = 0.012
        a.extrude(
            "Stock",
            self.outline(
                [
                    (s1, 0.012),
                    (s0 + 0.03, bh1 - 0.01, 0.01),
                    (s0, bh1, 0.008),
                    (s0, bh0, 0.008),
                    (s0 + t * 2, bh0, 0.006),
                    (s0 + t * 2, bh1 - t * 2.4),
                    (s0 + 0.04, bh1 - t * 2.6),
                    (s1, 0.012 - t),
                ]
            ),
            self.w(0.03),
            self.m["trim"],
            bevel=0.008,
        )
        a.extrude(
            "StockStrut",
            self.outline([(s0 + t * 2, bh0 + 0.01), (s1, -0.02), (s1, -0.02 - t), (s0 + t * 2, bh0 + 0.01 - t)]),
            self.w(0.026),
            self.m["trim"],
            bevel=0.006,
        )

    def _grip(self):
        a, k = self.a, self.k
        rake = math.radians(k["grip_rake"])
        top = k["receiver_h"][0] + 0.004
        gl = k["grip_len"]
        gu = k["grip_u"]
        th = 0.036  # front-to-back thickness
        du = -math.sin(rake) * gl  # the bottom sits further back
        dh = -math.cos(rake) * gl
        pts = [
            (gu - th * 0.55, top),
            (gu + th * 0.65, top),
            (gu + th * 0.55 + du * 0.25, top + dh * 0.25, 0.01),  # finger groove bumps
            (gu + th * 0.62 + du * 0.45, top + dh * 0.45, 0.012),
            (gu + th * 0.5 + du * 0.7, top + dh * 0.7, 0.012),
            (gu + th * 0.58 + du, top + dh, 0.01),
            (gu - th * 0.5 + du, top + dh - 0.004, 0.012),
            (gu - th * 0.62 + du * 0.5, top + dh * 0.5, 0.03),  # palm swell
        ]
        a.extrude("Grip", self.outline(pts), self.w(0.034), self.m["polymer"], bevel=0.012)
        # texture panel (stippling area) on both sides: a shallow recess
        for s, nm in ((1, "R"), (-1, "L")):
            a.cut(
                "Grip",
                a.extrude(
                    f"GripTexture{nm}",
                    self.outline([(gu - th * 0.25 + du * 0.25, top + dh * 0.25, 0.006), (gu + th * 0.3 + du * 0.25, top + dh * 0.25, 0.006), (gu + th * 0.25 + du * 0.8, top + dh * 0.8, 0.006), (gu - th * 0.3 + du * 0.8, top + dh * 0.8, 0.006)]),
                    self.w(0.008),
                    self.m["rubber"],
                    pos=(s * self.w(0.034) / 2, 0, 0),
                    bevel=0,
                ),
            )

    def _trigger(self):
        a, k = self.a, self.k
        top = k["receiver_h"][0]
        gu = k["grip_u"]
        u0, u1 = gu + 0.03, gu + 0.1
        bot = top - 0.042
        a.extrude(
            "TriggerGuard",
            self.outline([(u0, top + 0.002), (u0, bot + 0.008, 0.006), (u0 + 0.01, bot), (u1 - 0.01, bot, 0.012), (u1, top + 0.002, 0.004)]),
            self.w(0.014),
            self.m["trim"],
            bevel=0.004,
        )
        a.cut(
            "TriggerGuard",
            a.extrude(
                "TriggerGuardHole",
                self.outline([(u0 + 0.007, top - 0.001), (u0 + 0.007, bot + 0.012, 0.004), (u0 + 0.014, bot + 0.007), (u1 - 0.012, bot + 0.007, 0.008), (u1 - 0.006, top - 0.001)]),
                self.w(0.03),
                self.m["trim"],
                bevel=0,
            ),
        )
        a.extrude(
            "Trigger",
            self.outline([(u0 + 0.022, top), (u0 + 0.032, top), (u0 + 0.03, top - 0.018, 0.006), (u0 + 0.02, top - 0.03), (u0 + 0.024, top - 0.016)]),
            self.w(0.008),
            self.m["steel"],
            bevel=0.002,
        )

    def _mag_box(self):
        a, k = self.a, self.k
        u0, u1, bot = k["mag"]
        top = k["receiver_h"][0] + 0.004
        a.extrude(
            "Magazine",
            self.outline([(u0, top), (u1, top), (u1 - 0.003, bot + 0.006), (u0 + 0.003, bot + 0.006)]),
            self.w(0.034),
            self.m["polymer"],
            bevel=0.008,
        )
        a.extrude(
            "MagazinePlate",
            self.outline([(u0 - 0.004, bot + 0.008), (u1 + 0.004, bot + 0.008), (u1 + 0.002, bot, 0.004), (u0 - 0.002, bot, 0.004)]),
            self.w(0.038),
            self.m["trim"],
            bevel=0.006,
        )

    def _mag_curved(self):
        a, k = self.a, self.k
        u0, u1, bot = k["mag"]
        top = k["receiver_h"][0] - 0.02
        depth = top - bot
        curve = depth * 0.22  # how far forward the bottom swings (the classic banana curve)
        n = 6
        front, back = [], []
        for i in range(n + 1):
            t = i / n
            h = top - depth * t
            sweep = curve * t * t
            front.append((u1 + sweep, h))
            back.append((u0 + sweep * 0.85, h))
        pts = front + list(reversed(back))
        a.extrude("Magazine", self.outline(pts), self.w(0.032), self.m["polymer"], bevel=0.008)
        for i in range(3):
            t = 0.25 + i * 0.22
            h = top - depth * t
            a.cut(
                "Magazine",
                a.box(
                    f"MagazineRib{i}",
                    (self.w(0.04), 0.012 * self.L * 0.3, (u1 - u0) * self.L * 0.7),
                    (0, self.V(h), -self.U((u0 + u1) / 2 + curve * t * t * 0.92)),
                    self.m["trim"],
                    bevel=0,
                ),
            )

    def _mag_drum(self):
        a, k = self.a, self.k
        u0, u1, bot = k["mag"]
        r = (u1 - u0) * self.L * 1.25
        a.cylinder("Magazine", r, self.w(0.075), (0, self.V(k["receiver_h"][0]) - r * 0.95, -self.U((u0 + u1) / 2)), self.m["polymer"], axis="X", segments=20, bevel=0.02)

    def _mag_tube(self):
        a, k = self.a, self.k
        r = k["barrel_r"][0] * self.L * self.chunk
        u0, u1 = k["receiver"][1], k["barrel_end"] - 0.04
        a.cylinder("Magazine", r, (u1 - u0) * self.L, (0, self.V(-0.032), -self.U((u0 + u1) / 2)), self.m["steel"], axis="Z", segments=14)
        a.cylinder("MagazineCap", r * 1.15, 0.06 * self.L * 0.4, (0, self.V(-0.032), -self.U(u1)), self.m["trim"], axis="Z", segments=14)

    def _rail(self, u0, u1, name="Rail", h=None):
        a, k = self.a, self.k
        base_h = k["receiver_h"][1] if h is None else h
        y = self.V(base_h) + 0.012 * self.L * 0.25
        length = (u1 - u0) * self.L
        width = self.w(0.03)
        a.box(name, (width, 0.012 * self.L * 0.5, length), (0, y, -self.U((u0 + u1) / 2)), self.m["trim"], bevel=0.006)
        # picatinny slots: cut cross grooves across the top
        teeth = max(4, int(length / (0.012 * self.L)))
        step = length / teeth
        for i in range(1, teeth):
            z = -self.U(u0) - i * step
            a.cut(name, a.box(f"{name}Slot{i}", (width * 1.4, 0.012 * self.L * 0.3, step * 0.42), (0, y + 0.012 * self.L * 0.2, z), self.m["trim"], bevel=0))
        self.rail_top = base_h + 0.006

    def _optic_scope(self):
        a, k = self.a, self.k
        oh = k["optic_h"]
        self.sight_h = oh
        y = self.V(oh)
        r = 0.0125 * self.L * self.chunk
        ru, rf = k["receiver"][0] - 0.03, k["receiver"][1] + 0.1
        stations = [
            (-self.U(ru - 0.05), r * 1.55),
            (-self.U(ru - 0.02), r * 1.55),
            (-self.U(ru + 0.015), r),
            (-self.U(rf - 0.02), r),
            (-self.U(rf + 0.02), r * 1.9),
            (-self.U(rf + 0.09), r * 1.9),
            (-self.U(rf + 0.095), r * 1.75),
        ]
        a.loft("Scope", [(z, rr, rr, (0, y)) for z, rr in stations], self.m["trim"], axis="Z", segments=20)
        a.cylinder("ScopeLens", r * 1.6, 0.01, (0, y, -self.U(rf + 0.096)), self.m["glass"], axis="Z", segments=20, group="glass", bevel=0)
        a.cylinder("ScopeEyepiece", r * 1.35, 0.01, (0, y, -self.U(ru - 0.051)), self.m["glass"], axis="Z", segments=20, group="glass", bevel=0)
        mid = (ru + rf) / 2
        a.cylinder("ScopeTurret", r * 0.85, r * 1.5, (0, y + r * 1.55, -self.U(mid)), self.m["steel"], axis="Y", segments=14)
        a.cylinder("ScopeTurretSide", r * 0.85, r * 1.5, (r * 1.55, y, -self.U(mid)), self.m["steel"], axis="X", segments=14)
        rail = getattr(self, "rail_top", k["receiver_h"][1])
        for i, uu in enumerate((ru + 0.04, rf - 0.04)):
            a.cylinder(f"ScopeRing{i}", r * 1.3, 0.016 * self.L, (0, y, -self.U(uu)), self.m["steel"], axis="Z", segments=16)
            ring_bottom = y - r * 1.2
            base_top = self.V(rail) - 0.008 * self.L  # sink the foot INTO the rail
            a.box(f"ScopeMount{i}", (r * 1.6, ring_bottom - base_top + 0.004 * self.L, 0.016 * self.L), (0, (ring_bottom + base_top) / 2, -self.U(uu)), self.m["steel"], bevel=0.006)

    def _optic_compact(self):
        """A compact sniper scope: short tube, a big objective bell, knurled turrets, low mounts."""
        import rbx_parts as P

        a, k = self.a, self.k
        oh = k["optic_h"]
        self.sight_h = oh
        y = self.V(oh)
        r = 0.013 * self.L
        u0 = k["receiver"][0] + 0.02
        u1 = u0 + 0.2
        stations = [
            (-self.U(u0 - 0.02), r * 1.45),
            (-self.U(u0 + 0.01), r * 1.45),
            (-self.U(u0 + 0.03), r),
            (-self.U(u1 - 0.05), r),
            (-self.U(u1 - 0.02), r * 2.1),
            (-self.U(u1 + 0.03), r * 2.1),
            (-self.U(u1 + 0.034), r * 1.95),
        ]
        a.loft("Scope", [(z, rr, rr, (0, y)) for z, rr in stations], self.m["trim"], axis="Z", segments=20)
        a.cylinder("ScopeLens", r * 1.85, 0.01, (0, y, -self.U(u1 + 0.035)), self.m["glass"], axis="Z", segments=20, group="glass", bevel=0)
        a.cylinder("ScopeEyepiece", r * 1.3, 0.01, (0, y, -self.U(u0 - 0.021)), self.m["glass"], axis="Z", segments=20, group="glass", bevel=0)
        mid = (u0 + u1) / 2
        a.cylinder("ScopeTurret", r * 0.8, r * 1.4, (0, y + r * 1.4, -self.U(mid)), self.m["steel"], axis="Y", segments=14)
        P.knurl(a, "ScopeTurret", (0, y + r * 1.9, -self.U(mid)), self.m["trim"], axis="Y", radius=r * 0.85, length=r * 0.8, rings=3)
        a.cylinder("ScopeTurretSide", r * 0.8, r * 1.4, (r * 1.4, y, -self.U(mid)), self.m["steel"], axis="X", segments=14)
        a.cylinder("ScopeRingGlow", r * 2.12, 0.006 * self.L, (0, y, -self.U(u1 - 0.005)), self.m["glow"], axis="Z", segments=20, bevel=0)
        rail = getattr(self, "rail_top", k["receiver_h"][1])
        for i, uu in enumerate((u0 + 0.04, u1 - 0.07)):
            a.cylinder(f"ScopeRing{i}", r * 1.25, 0.014 * self.L, (0, y, -self.U(uu)), self.m["steel"], axis="Z", segments=16)
            ring_bottom = y - r * 1.15
            base_top = self.V(rail) - 0.01 * self.L  # sink the foot INTO the rail/body: mounted, not hovering
            a.box(f"ScopeMount{i}", (r * 1.6, ring_bottom - base_top + 0.004 * self.L, 0.016 * self.L), (0, (ring_bottom + base_top) / 2, -self.U(uu)), self.m["steel"], bevel=0.006)

    def _optic_tactical(self):
        """A short, chunky sci-fi sight: a faceted (8-sided) housing, a big objective bell with a lit ring, faceted
        turrets, on ONE wide block mount with a cross-bolt — the modern AAA look (not a long hunting scope)."""
        import rbx_parts as P

        a, k = self.a, self.k
        oh = k["optic_h"] - 0.004
        self.sight_h = oh
        y = self.V(oh)
        r = 0.0165 * self.L
        u0 = k["receiver"][0] + 0.075  # over the front half of the receiver
        u1 = u0 + 0.12
        z = lambda u: -self.U(u)  # noqa: E731
        stations = [
            (z(u0 - 0.004), r * 1.05),
            (z(u0 + 0.004), r * 1.25),
            (z(u0 + 0.03), r * 1.25),
            (z(u0 + 0.042), r * 1.12),
            (z(u1 - 0.045), r * 1.12),
            (z(u1 - 0.025), r * 1.75),
            (z(u1 + 0.004), r * 1.8),
            (z(u1 + 0.008), r * 1.68),
        ]
        a.loft("Scope", [(zz, rr, rr, (0, y)) for zz, rr in stations], self.m["trim"], axis="Z", segments=8)
        a.cylinder("ScopeLens", r * 1.5, 0.01, (0, y, z(u1 + 0.009)), self.m["glass"], axis="Z", segments=24, group="glass", bevel=0)
        a.cylinder("ScopeEyepiece", r * 0.9, 0.01, (0, y, z(u0 - 0.005)), self.m["glass"], axis="Z", segments=24, group="glass", bevel=0)
        a.cylinder("ScopeRingGlow", r * 1.82, 0.005 * self.L, (0, y, z(u1 - 0.006)), self.m["glow"], axis="Z", segments=24, bevel=0)
        mid = (u0 + 0.042 + u1 - 0.045) / 2
        a.cylinder("ScopeTurret", r * 0.75, r * 1.3, (0, y + r * 1.4, z(mid)), self.m["steel"], axis="Y", segments=8, bevel=0.004)
        a.cylinder("ScopeTurretCap", r * 0.82, r * 0.4, (0, y + r * 2.0, z(mid)), self.m["trim"], axis="Y", segments=8, bevel=0.003)
        a.cylinder("ScopeTurretSide", r * 0.75, r * 1.3, (r * 1.4, y, z(mid)), self.m["steel"], axis="X", segments=8, bevel=0.004)
        # one wide block mount, sunk into the rail, with a cross-bolt and two screws
        rail = getattr(self, "rail_top", k["receiver_h"][1])
        body_bottom = y - r * 1.05
        base_top = self.V(rail) - 0.008 * self.L
        mu = (u0 + 0.004 + u1 - 0.045) / 2
        a.box("ScopeMount", (r * 2.3, body_bottom - base_top + 0.004 * self.L, self.zs(u0 + 0.01, u1 - 0.04)), (0, (body_bottom + base_top) / 2, z(mu)), self.m["steel"], bevel=0.006)
        a.cylinder("ScopeCrossBolt", 0.006 * self.L, r * 2.5, (0, (body_bottom + base_top) / 2 - 0.002 * self.L, z(mu)), self.m["trim"], axis="X", segments=8, bevel=0.002)
        with a.floaters():
            P.screws(a, "ScopeMountScrew", [(r * 1.15, (body_bottom + base_top) / 2 + 0.006 * self.L, z(uu)) for uu in (u0 + 0.025, u1 - 0.055)], self.m["steel"], facing="+X", radius=0.01)

    def _optic_hooded(self):
        """A short, fat ROUND scope in glossy black (the 'Reaper' reference): a flared objective with a DEEP lens hood
        (the glass set well back inside it), a narrower neck, thin bands, a turret block with round knurled knobs on
        top and side, on ONE low clamp mount with a side knob — sitting near the rear of the rail."""
        import rbx_parts as P

        a, k = self.a, self.k
        gloss = self.m.get("gloss", self.m["trim"])
        rail = getattr(self, "rail_top", k["receiver_h"][1])
        r = 0.0185 * self.L
        u0 = k["receiver"][0] + 0.03
        u1 = u0 + 0.115
        z = lambda u: -self.U(u)  # noqa: E731
        oh = rail + 0.011 + r / self.L
        self.sight_h = oh
        y = self.V(oh)
        stations = [
            (z(u0 - 0.006), r * 0.92),
            (z(u0), r * 1.0),
            (z(u0 + 0.024), r * 1.0),
            (z(u0 + 0.03), r * 0.86),
            (z(u1 - 0.046), r * 0.86),
            (z(u1 - 0.03), r * 1.2),
            (z(u1), r * 1.24),
        ]
        a.loft("Scope", [(zz, rr, rr, (0, y)) for zz, rr in stations], gloss, axis="Z", segments=28)
        hood = 0.024 * self.L
        a.cut("Scope", a.cylinder("ScopeHood", r * 1.04, hood * 2, (0, y, z(u1)), gloss, axis="Z", segments=28, bevel=0))
        a.cylinder("ScopeLens", r * 1.05, 0.01, (0, y, z(u1) + hood - 0.006), self.m["glass"], axis="Z", segments=28, group="glass", bevel=0)
        a.cylinder("ScopeEyepiece", r * 0.8, 0.01, (0, y, z(u0 - 0.006) + 0.003), self.m["glass"], axis="Z", segments=28, group="glass", bevel=0)
        for j, (uu, rr) in enumerate(((u0 + 0.01, r * 1.025), (u0 + 0.034, r * 0.885), (u1 - 0.05, r * 0.885), (u1 - 0.008, r * 1.265))):
            a.cylinder(f"ScopeBand{j}", rr, 0.0035 * self.L, (0, y, z(uu)), self.m["trim"], axis="Z", segments=28, bevel=0)
        # turret block on the neck: a rounded saddle with knurled round knobs on top and on the right side
        mid = (u0 + 0.03 + u1 - 0.046) / 2
        a.box("ScopeSaddle", (r * 1.75, r * 1.1, self.zs(mid - 0.012, mid + 0.012)), (0, y + r * 0.3, z(mid)), gloss, bevel=0.006)
        a.cylinder("ScopeTurret", r * 0.48, r * 0.55, (0, y + r * 1.1, z(mid)), gloss, axis="Y", segments=20, bevel=0.003)
        P.knurl(a, "ScopeTurretGrip", (0, y + r * 1.12, z(mid)), self.m["trim"], axis="Y", radius=r * 0.5, length=r * 0.3, rings=3)
        a.cylinder("ScopeTurretSide", r * 0.42, r * 0.5, (r * 1.05, y + r * 0.2, z(mid)), gloss, axis="X", segments=20, bevel=0.003)
        P.knurl(a, "ScopeSideGrip", (r * 1.12, y + r * 0.2, z(mid)), self.m["trim"], axis="X", radius=r * 0.44, length=r * 0.25, rings=3)
        # one low clamp mount on the rail (sunk into the fins), with a cross knob on the left
        body_bottom = y - r * 0.82
        base_top = self.V(rail) - 0.007 * self.L
        mu = u0 + 0.06
        a.box("ScopeMount", (r * 1.6, body_bottom - base_top + 0.004 * self.L, self.zs(mu - 0.017, mu + 0.017)), (0, (body_bottom + base_top) / 2, z(mu)), gloss, bevel=0.005)
        a.box("ScopeClamp", (r * 2.0, 0.008 * self.L, self.zs(mu - 0.02, mu + 0.02)), (0, base_top + 0.004 * self.L, z(mu)), self.m["trim"], bevel=0.003)
        a.cylinder("ScopeClampKnob", 0.0065 * self.L, r * 0.6, (-r * 1.15, base_top + 0.004 * self.L, z(mu)), self.m["steel"], axis="X", segments=14, bevel=0.002)

    def _optic_reddot(self):
        a, k = self.a, self.k
        oh = k["optic_h"]
        self.sight_h = oh
        uc = k["receiver"][0] + (k["receiver"][1] - k["receiver"][0]) * 0.4
        rail = getattr(self, "rail_top", k["receiver_h"][1])
        a.extrude(
            "Optic",
            self.outline([(uc - 0.035, rail), (uc + 0.035, rail), (uc + 0.03, oh + 0.022, 0.012), (uc - 0.03, oh + 0.022, 0.012)]),
            self.w(0.036),
            self.m["trim"],
            bevel=0.01,
        )
        a.cut(
            "Optic",
            a.cylinder("OpticWindow", 0.014 * self.L, 0.2 * self.L, (0, self.V(oh), -self.U(uc)), self.m["trim"], axis="Z", segments=16, bevel=0),
        )
        a.cylinder("OpticLens", 0.0145 * self.L, 0.004, (0, self.V(oh), -self.U(uc + 0.03)), self.m["glass"], axis="Z", segments=16, group="glass", bevel=0)

    def _optic_holo(self):
        a, k = self.a, self.k
        oh = k["optic_h"]
        self.sight_h = oh
        uc = k["receiver"][0] + (k["receiver"][1] - k["receiver"][0]) * 0.35
        rail = getattr(self, "rail_top", k["receiver_h"][1])
        a.extrude(
            "Optic",
            self.outline([(uc - 0.05, rail), (uc + 0.05, rail), (uc + 0.05, oh + 0.03, 0.01), (uc + 0.03, oh + 0.035), (uc - 0.05, oh + 0.035, 0.01)]),
            self.w(0.04),
            self.m["trim"],
            bevel=0.01,
        )
        a.cut(
            "Optic",
            a.box("OpticWindow", (self.w(0.03), 0.034 * self.L, 0.2 * self.L), (0, self.V(oh + 0.008), -self.U(uc)), self.m["trim"], bevel=0),
        )
        a.box("OpticLens", (self.w(0.03), 0.034 * self.L, 0.004), (0, self.V(oh + 0.008), -self.U(uc + 0.045)), self.m["glass"], group="glass", bevel=0)

    def _optic_irons(self):
        a, k = self.a, self.k
        self.sight_h = k["optic_h"]
        top = k["receiver_h"][1]
        a.extrude(
            "RearSight",
            self.outline([(k["receiver"][0] + 0.03, top), (k["receiver"][0] + 0.06, top), (k["receiver"][0] + 0.055, k["optic_h"]), (k["receiver"][0] + 0.035, k["optic_h"])]),
            self.w(0.03),
            self.m["trim"],
            bevel=0.004,
        )
        fu = k["barrel_end"] - 0.02
        a.box("FrontSight", (self.w(0.008), (k["optic_h"] - 0.004) * self.L * 0.6, 0.012 * self.L), (0, self.V(k["optic_h"] * 0.55), -self.U(fu)), self.m["trim"], bevel=0.002)

    def _bolt(self):
        a, k = self.a, self.k
        u = k["receiver"][0] + (k["receiver"][1] - k["receiver"][0]) * 0.22
        x = self.w(k["width"]) / 2
        y = self.V(k["receiver_h"][1] - 0.01)
        knob = 0.012 * self.L
        a.tube("BoltHandle", [(x * 0.6, y, -self.U(u)), (x + knob * 1.5, y - knob * 0.8, -self.U(u - 0.005)), (x + knob * 2.2, y - knob * 2.2, -self.U(u - 0.01))], knob * 0.32, self.m["steel"], segments=8)
        a.sphere("BoltKnob", knob, (x + knob * 2.3, y - knob * 2.5, -self.U(u - 0.012)), self.m["steel"], segments=14, rings=8)
        a.anchor("Bolt", (x + knob * 2.3, y - knob * 2.5, -self.U(u - 0.012)))

    def _bipod(self):
        a, k = self.a, self.k
        u = k["handguard"][1] - 0.03
        y = self.V(-0.04)
        a.box("BipodMount", (self.w(0.03), 0.02 * self.L * 0.6, 0.03 * self.L), (0, y - 0.006 * self.L, -self.U(u)), self.m["trim"], bevel=0.006)
        leg = 0.2 * self.L
        for s, nm in ((1, "R"), (-1, "L")):
            foot = (s * leg * 0.32, y - leg * 0.92, -self.U(u) - leg * 0.3)
            a.tube(f"BipodLeg{nm}", [(s * 0.004 * self.L, y - 0.01 * self.L, -self.U(u)), foot], 0.0055 * self.L, self.m["steel"], segments=8)
            a.sphere(f"BipodFoot{nm}", 0.009 * self.L, foot, self.m["rubber"], segments=10, rings=6)

    def _scifi_detail(self):
        """Sci-fi read: glowing strips along the receiver + handguard, both sides."""
        a, k = self.a, self.k
        u0, u1 = k["receiver"]
        for s, nm in ((1, "R"), (-1, "L")):
            a.box(
                f"GlowStrip{nm}",
                (self.w(0.004), 0.006 * self.L, (u1 - u0) * self.L * 0.55),
                self.at(u0 + (u1 - u0) * 0.55, k["receiver_h"][1] - 0.012, side=s * 1.03),
                self.m["glow"],
                bevel=0,
            )
        if self.parts["handguard"] in ("slotted", "railed"):
            h0, h1 = k["handguard"]
            for s, nm in ((1, "R"), (-1, "L")):
                a.box(
                    f"HandguardGlow{nm}",
                    (self.w(0.004), 0.005 * self.L, (h1 - h0) * self.L * 0.5),
                    (s * self.w(k["width"] * 1.1) / 2, self.V(0.012), -self.U((h0 + h1) / 2)),
                    self.m["glow"],
                    bevel=0,
                )

    # ------------------------------------------------------------------ proportion checks
    def _checks(self):
        from rbx_critic import _check

        k = self.k
        out = []

        def rng(name, value, lo, hi, fix):
            out.append(
                _check(
                    f"firearm.{name}",
                    lo <= value <= hi,
                    round(value, 3),
                    f"{lo}-{hi}",
                    fix,
                    severity="warning",
                )
            )

        exposed = k["barrel_end"] - (k["handguard"][1] if self.parts["handguard"] != "none" else k["receiver"][1])
        lo, hi = RANGES["barrel_exposed"][self.kind]
        rng("barrel_exposed", exposed, lo, hi, f"a {self.kind}'s exposed barrel is {lo}-{hi} of its length: tune(barrel_end=..., handguard=(...))")
        rng("grip_len", k["grip_len"], *RANGES["grip_len"], "grip length outside real ratios: tune(grip_len=...)")
        rng("grip_rake", k["grip_rake"], *RANGES["grip_rake"], "grips rake back 8-28 degrees: tune(grip_rake=...)")
        if self.parts["stock"] != "none":
            rng("stock_len", k["stock"][1] - k["stock"][0], *RANGES["stock_len"], "stock length outside real ratios: tune(stock=(0, ...))")
        rng("receiver_len", k["receiver"][1] - k["receiver"][0], *RANGES["receiver_len"], "receiver length outside real ratios: tune(receiver=(...))")
        self.a.checks += out

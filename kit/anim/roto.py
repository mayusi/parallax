"""roto.py - POSE BY POINTING (board ywjg, AAA gaps v2 A3; board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md).

The only poses the owner has loved are his OWN (Katana4Kiriage 2 -> 9 once his joint rotations were copied verbatim;
vault rule "copy the owner's poses exactly"). Animating them on his rig is slow; pointing is fast: open ANY picture
(an anime frame, a loved Roblox game's frame, a photo), click the joints, and the kit fits an R6 pose to them.

R6 limbs are rigid sticks of known length (arms / legs 2 studs, torso 2), so a limb's depth comes from how short it
looks on screen; the one thing a single picture cannot tell - does the limb point TOWARD or AWAY from the camera -
is solved both ways and offered as a per-limb FLIP in the page (with a live 3D R6 preview to judge it).

The fit (least squares, the kit's own R6 forward kinematics, kit/anim/clip.py): an orthographic camera (rotation,
scale, offset) + the torso's rotation and height + each arm / leg / the head's rotation (character space, the clip
format), regularised toward small rotations (a limb's twist about its own axis is invisible in a picture). Multi-start
over the camera side and every limb's depth sign; the best fit and its flip alternates are kept.

    python kit/anim/roto.py fit <picture> --clicks <clicks.json> --as <Pose>   fit + write assets/animations/poses/<Pose>.roto.json
    python kit/anim/roto.py serve <picture> --as <Pose> [--port 8767]       the click page (lune run kit anim roto ...)
The pose file holds every joint as a clip frame [qx, qy, qz, qw, x, y, z] + an `arms_pose` (strike keys take it as is:
kit/anim/strike.py apply_arm_poses) + the reprojection error.
"""
import base64
import http.server
import itertools
import json
import math
import os
import sys
import threading

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clip as C  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
POSES = os.path.join("assets", "animations", "poses")
# the clickable points: (part, a point in the part's own frame); "right" = the CHARACTER's right
KP = {
    "head": ("Head", (0.0, 0.0, 0.0)),
    "neck": ("Torso", (0.0, 1.0, 0.0)),
    "pelvis": ("Torso", (0.0, -1.0, 0.0)),
    "r_shoulder": ("Right Arm", (0.0, 0.8, 0.0)),
    "r_hand": ("Right Arm", (0.0, -1.0, 0.0)),
    "l_shoulder": ("Left Arm", (0.0, 0.8, 0.0)),
    "l_hand": ("Left Arm", (0.0, -1.0, 0.0)),
    "r_hip": ("Right Leg", (0.0, 0.8, 0.0)),
    "r_foot": ("Right Leg", (0.0, -1.0, 0.0)),
    "l_hip": ("Left Leg", (0.0, 0.8, 0.0)),
    "l_foot": ("Left Leg", (0.0, -1.0, 0.0)),
}
ORDER = list(KP)
LABELS = {"head": "head (centre)", "neck": "neck (top of the torso)", "pelvis": "pelvis (bottom of the torso)",
          "r_shoulder": "the character's RIGHT shoulder", "r_hand": "the character's RIGHT hand",
          "l_shoulder": "the character's LEFT shoulder", "l_hand": "the character's LEFT hand",
          "r_hip": "the character's RIGHT hip", "r_foot": "the character's RIGHT foot",
          "l_hip": "the character's LEFT hip", "l_foot": "the character's LEFT foot"}
LIMBS = {"Right Arm": "r_hand", "Left Arm": "l_hand", "Right Leg": "r_foot", "Left Leg": "l_foot"}
PARTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
_RIG = None


def rig():
    global _RIG
    if _RIG is None:
        _RIG = C.load_rig("r6", ROOT)
    return _RIG


def rotvec(v):
    v = np.asarray(v, dtype=float)
    a = float(np.linalg.norm(v))
    if a < 1e-12:
        return np.eye(3)
    k = v / a
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


# params: cam rv (3), log scale, tx, ty, torso rv (3), torso dy, then rv (3) for Right Arm, Left Arm, Right Leg,
# Left Leg, Head
N = 3 + 1 + 2 + 3 + 1 + 15
SLOT = {"Right Arm": 10, "Left Arm": 13, "Right Leg": 16, "Left Leg": 19, "Head": 22}


def transforms(p):
    tr = {"Torso": (rotvec(p[6:9]), np.array([0.0, p[9], 0.0]))}
    for part, i in SLOT.items():
        tr[part] = (rotvec(p[i:i + 3]), np.zeros(3))
    return tr


def world_points(p):
    W = C.fk(rig(), transforms(p))
    return {k: (W[part] @ np.array([*pt, 1.0]))[:3] for k, (part, pt) in KP.items()}, W


def project(p, X):
    """orthographic: camera-space (x right, y up, z toward the camera); image units = image heights"""
    Rc = rotvec(p[0:3])
    c = Rc @ X
    s = math.exp(p[3])
    return np.array([s * c[0] + p[4], s * c[1] + p[5]]), c[2]


def residuals(p, clicks, flips):
    pts, _ = world_points(p)
    r = []
    for k, uv in clicks.items():
        q, _ = project(p, pts[k])
        r.extend((q - np.asarray(uv)) * 10.0)
    # depth signs asked for (a limb pointing toward +1 / away -1 from the camera)
    s = math.exp(p[3])
    for limb, f in (flips or {}).items():
        if f and limb in LIMBS:
            top = KP[LIMBS[limb].replace("hand", "shoulder").replace("foot", "hip")][0]
            a = pts[{"Right Arm": "r_shoulder", "Left Arm": "l_shoulder", "Right Leg": "r_hip", "Left Leg": "l_hip"}[limb]]
            b = pts[LIMBS[limb]]
            dz = (rotvec(p[0:3]) @ (b - a))[2] * s
            r.append(max(0.0, -f * dz + 0.02) * 20.0)
            del top
    # small rotations preferred (a twist is invisible); the head stays near the torso; camera roll small
    for part, i in SLOT.items():
        r.extend(p[i:i + 3] * (0.25 if part == "Head" else 0.04))
    r.append(p[9] * 0.3)
    r.append(rotvec(p[0:3])[0, 1] * 0.2)
    return np.array(r)


def normalise(clicks_px, width, height):
    """pixels (y down) -> image heights, centred, y up"""
    return {k: ((x - width / 2) / height, -(y - height / 2) / height) for k, (x, y) in clicks_px.items() if k in KP}


def _start(cam_yaw, signs, clicks):
    p = np.zeros(N)
    p[0:3] = [0.0, math.radians(cam_yaw), 0.0]
    if "neck" in clicks and "pelvis" in clicks:
        d = np.linalg.norm(np.subtract(clicks["neck"], clicks["pelvis"]))
        p[3] = math.log(max(d / 2.0, 1e-3))
        mid = np.add(clicks["neck"], clicks["pelvis"]) / 2
        p[4], p[5] = mid
    else:
        p[3] = math.log(0.1)
    for (part, i), sgn in zip([(k, SLOT[k]) for k in ("Right Arm", "Left Arm", "Right Leg", "Left Leg")], signs):
        p[i] = 0.6 * sgn                                    # a nudge forward / back about X: picks the depth branch
    return p


def depth_signs(p):
    pts, _ = world_points(p)
    Rc = rotvec(p[0:3])
    out = {}
    for limb, a in (("Right Arm", "r_shoulder"), ("Left Arm", "l_shoulder"), ("Right Leg", "r_hip"), ("Left Leg", "l_hip")):
        out[limb] = 1 if (Rc @ (pts[LIMBS[limb]] - pts[a]))[2] >= 0 else -1
    return out


def facing_yaws(clicks):
    """the camera side read from the clicks: the character's RIGHT shoulder on the viewer's LEFT = it faces the camera"""
    if "r_shoulder" in clicks and "l_shoulder" in clicks:
        front = clicks["r_shoulder"][0] < clicks["l_shoulder"][0]
        return (150, 210) if front else (-30, 30)
    return (180, 0)


def _solve(p0, clicks, flips):
    sol = least_squares(residuals, p0, args=(clicks, flips), method="trf", max_nfev=250)
    pts, _ = world_points(sol.x)
    err = math.sqrt(np.mean([np.sum((project(sol.x, pts[k])[0] - np.asarray(uv)) ** 2) for k, uv in clicks.items()]))
    return err, sol.cost, sol.x


def fit(clicks, flips=None, starts=None):
    """clicks: {kp: (u, v)} in image heights (normalise()); flips: {limb: +1 toward / -1 away / None}. -> best result,
    alternates (other depth patterns, sorted by error).
    Fast route (one page fit in a few seconds, not 40): the camera side from the clicks, one solve per side with no
    depth wish, then each limb flipped ONCE from the best (a limb's depth sign is near independent of the others')"""
    if len(clicks) < 6:
        raise ValueError(f"click at least 6 points (have {len(clicks)}): neck, pelvis, both shoulders, both hands at least")
    results = []
    for yaw in starts or facing_yaws(clicks):
        for signs in ((1, 1, 1, 1), (-1, -1, 1, 1)):
            results.append(_solve(_start(yaw, signs, clicks), clicks, flips))
    results.sort(key=lambda r: (round(r[0], 4), r[1]))
    base = results[0]
    signs0 = depth_signs(base[2])
    for limb in LIMBS:
        if (flips or {}).get(limb):
            continue                                       # the owner already chose this limb's side
        want = dict(flips or {}, **{limb: -signs0[limb]})
        results.append(_solve(base[2].copy(), clicks, want))
    results.sort(key=lambda r: (round(r[0], 4), r[1]))
    best = results[0]
    seen, alts = set(), []
    for err, cost, x in results:
        key = tuple(depth_signs(x).values())
        if key in seen:
            continue
        seen.add(key)
        alts.append({"error": err, "params": x, "signs": depth_signs(x)})
    return {"error": best[0], "params": best[2], "signs": depth_signs(best[2])}, alts


def pose_record(params, clicks, picture, name, error):
    tr = transforms(params)
    frames = {part: [round(float(v), 6) for v in list(C.mat_quat(R)) + list(p)] for part, (R, p) in tr.items()}
    return {"schema": 1, "name": name, "picture": picture, "made_by": "kit/anim/roto.py (pose by pointing)",
            "clicks": {k: [round(float(a), 5) for a in v] for k, v in clicks.items()},
            "reprojection_error_image_heights": round(float(error), 5),
            "camera": {"rotvec": [round(float(v), 5) for v in params[0:3]], "scale": round(math.exp(params[3]), 5)},
            "frames": frames, "arms_pose": {"Right Arm": frames["Right Arm"], "Left Arm": frames["Left Arm"]},
            "loved_space_deg": loved_space(frames),
            "use": "a strike key's arms_pose takes `arms_pose` as is (kit/anim/strike.py); `frames` are the whole body in the clip format"}


def loved_space(frames):
    """how far the pose sits from the learned space of LOVED R6 poses (kit/anim/pose_space.py; deg/joint - the loved
    clips stay under 24, kit anim appeal warns past 26.2) or None where the space is not built (AAA gaps v2 E5)"""
    try:
        import pose_space as PS
        PS.load()
        return round(float(PS.distance({j: v for j, v in frames.items() if j in PS.JOINTS})), 2)
    except (ImportError, OSError, KeyError, ValueError):
        return None


def boxes(params):
    """each part's 8 corners in character space (the page draws the 3D preview and the overlay from them)"""
    _, W = world_points(params)
    sizes = rig()["sizes"]
    out = {}
    for part in PARTS:
        sx, sy, sz = (v / 2 for v in sizes[part])
        out[part] = [list((W[part] @ np.array([x, y, z, 1.0]))[:3]) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]
    return out


def overlay(params):
    """the boxes' corners projected into the picture (image heights, y up)"""
    return {part: [list(project(params, np.array(c))[0]) for c in cs] for part, cs in boxes(params).items()}


# ---------------------------------------------------------------- the click page
PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>kit anim roto</title>
<style>body{margin:0;background:#15161c;color:#e8e8ee;font:14px system-ui;display:flex;gap:12px;padding:12px}
#left{position:relative}canvas{background:#000;border-radius:6px}#side{width:340px}button{margin:3px 2px;padding:6px 10px;
background:#2b2e3a;color:#eee;border:1px solid #444;border-radius:5px;cursor:pointer}button.on{background:#3d6fd1}
.k{padding:2px 0}.k.done{color:#7ad17a}.k.next{color:#ffd24d;font-weight:600}#err{font-weight:600}</style></head><body>
<div id="left"><canvas id="c"></canvas></div><div id="side"><h3>Pose by pointing: __NAME__</h3>
<div>Click each point on the picture in this order (right / left = the CHARACTER's).</div><div id="list"></div>
<div><button id="undo">Undo</button><button id="skip">Skip point</button><button id="fit">Fit R6</button></div>
<div id="err"></div><div id="flips"></div><canvas id="p3" width="320" height="320"></canvas>
<div>Turn the preview: <input id="yaw" type="range" min="-180" max="180" value="30"></div>
<div><button id="save">Save pose</button></div><div id="msg"></div></div>
<script>
const ORDER=__ORDER__, LABELS=__LABELS__; const img=new Image(); const TK="__TOKEN__"; img.src="/picture?t="+TK;
const c=document.getElementById("c"), g=c.getContext("2d"); let clicks={}, i=0, fitRes=null, flips={};
function next(){while(i<ORDER.length&&clicks[ORDER[i]]===null)i++;}
function list(){document.getElementById("list").innerHTML=ORDER.map((k,j)=>`<div class="k ${k in clicks?'done':(j==i?'next':'')}">${j+1}. ${LABELS[k]}</div>`).join("")}
img.onload=()=>{const s=Math.min(1,(window.innerHeight-24)/img.height,(window.innerWidth-380)/img.width);c.width=img.width*s;c.height=img.height*s;draw();list();};
function toPx(u,v){return [u*c.height+c.width/2, -v*c.height+c.height/2]}
function draw(){g.drawImage(img,0,0,c.width,c.height);
 if(fitRes){g.strokeStyle="rgba(80,170,255,.9)";g.lineWidth=1.5;for(const [part,cs] of Object.entries(fitRes.overlay)){const E=[[0,1],[2,3],[4,5],[6,7],[0,2],[1,3],[4,6],[5,7],[0,4],[1,5],[2,6],[3,7]];for(const [a,b] of E){const A=toPx(...cs[a]),B=toPx(...cs[b]);g.beginPath();g.moveTo(...A);g.lineTo(...B);g.stroke();}}}
 for(const [k,p] of Object.entries(clicks)){if(!p)continue;g.fillStyle=k.startsWith("r_")?"#ff5a5a":(k.startsWith("l_")?"#5aff8c":"#ffd24d");g.beginPath();g.arc(p[0],p[1],5,0,7);g.fill();}}
c.onclick=e=>{if(i>=ORDER.length)return;const r=c.getBoundingClientRect();clicks[ORDER[i]]=[e.clientX-r.left,e.clientY-r.top];i++;next();draw();list();};
document.getElementById("undo").onclick=()=>{if(i>0){i--;delete clicks[ORDER[i]];}draw();list();};
document.getElementById("skip").onclick=()=>{if(i<ORDER.length){clicks[ORDER[i]]=null;i++;}list();};
async function doFit(){const pts={};for(const [k,p] of Object.entries(clicks))if(p)pts[k]=p;
 const r=await fetch("/fit?t="+TK,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({clicks:pts,width:c.width,height:c.height,flips})});fitRes=await r.json();
 if(fitRes.error_msg){document.getElementById("err").textContent=fitRes.error_msg;return;}
 document.getElementById("err").textContent=`fit error: ${(fitRes.error*100).toFixed(1)}% of the picture height`;
 document.getElementById("flips").innerHTML=Object.keys(fitRes.signs).map(l=>`<button data-l="${l}">${l}: ${fitRes.signs[l]>0?"toward camera":"away"} (flip)</button>`).join("");
 for(const b of document.querySelectorAll("#flips button"))b.onclick=()=>{const l=b.dataset.l;flips[l]=-fitRes.signs[l];document.getElementById("err").textContent="fitting...";doFit();};
 draw();p3();}
document.getElementById("fit").onclick=()=>{document.getElementById("err").textContent="fitting...";doFit();};
function p3(){const q=document.getElementById("p3").getContext("2d");q.fillStyle="#0b0c10";q.fillRect(0,0,320,320);if(!fitRes)return;
 const a=document.getElementById("yaw").value*Math.PI/180,co=Math.cos(a),si=Math.sin(a);q.strokeStyle="#9fc4ff";
 const P=v=>[160+(v[0]*co-v[2]*si)*40,190-v[1]*40];const E=[[0,1],[2,3],[4,5],[6,7],[0,2],[1,3],[4,6],[5,7],[0,4],[1,5],[2,6],[3,7]];
 for(const cs of Object.values(fitRes.boxes))for(const [x,y] of E){q.beginPath();q.moveTo(...P(cs[x]));q.lineTo(...P(cs[y]));q.stroke();}}
document.getElementById("yaw").oninput=p3;
document.getElementById("save").onclick=async()=>{const r=await fetch("/save?t="+TK,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});const j=await r.json();document.getElementById("msg").textContent=j.msg;};
</script></body></html>"""


NAME_OK = __import__("re").compile(r"^[A-Za-z0-9_-]{1,64}$")


def serve(picture, name, port=8767):
    """the click page on 127.0.0.1 only; a per-launch TOKEN in the URL guards every request, Host / Origin must be this
    server, POSTs must be JSON (security review 2026-10-22: a page elsewhere could otherwise drive /fit and /save)"""
    import html
    import secrets
    if not NAME_OK.match(name):
        raise ValueError(f"pose name {name!r}: letters, digits, _ and - only")
    pic = open(picture, "rb").read()
    ctype = "image/png" if picture.lower().endswith(".png") else "image/jpeg"
    state = {"last": None}
    token = secrets.token_urlsafe(18)
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ct):
            self.send_response(code)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _ok(self):
            from urllib.parse import parse_qs, urlparse
            if self.headers.get("Host") not in hosts:
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {f"http://{h}" for h in hosts}:
                return False
            q = parse_qs(urlparse(self.path).query)
            return secrets.compare_digest((q.get("t") or [""])[0], token)

        def do_GET(self):
            if not self._ok():
                return self._send(403, b"forbidden", "text/plain")
            route = self.path.split("?")[0]
            if route == "/picture":
                return self._send(200, pic, ctype)
            page = (PAGE.replace("__NAME__", html.escape(name)).replace("__ORDER__", json.dumps(ORDER))
                    .replace("__LABELS__", json.dumps(LABELS)).replace("__TOKEN__", token))
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self):
            if not self._ok() or not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._send(403, b"{}", "application/json")
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 1 << 20)) or b"{}")
            route = self.path.split("?")[0]
            if route == "/fit":
                try:
                    clicks = normalise({k: v for k, v in body["clicks"].items()}, body["width"], body["height"])
                    best, _ = fit(clicks, {k: v for k, v in (body.get("flips") or {}).items() if v})
                except (ValueError, KeyError, TypeError) as exc:
                    return self._send(200, json.dumps({"error_msg": str(exc)}).encode(), "application/json")
                state["last"] = (best, clicks)
                out = {"error": best["error"], "signs": best["signs"], "overlay": overlay(best["params"]),
                       "boxes": boxes(best["params"])}
                return self._send(200, json.dumps(out).encode(), "application/json")
            if route == "/save":
                if not state["last"]:
                    return self._send(200, json.dumps({"msg": "fit first"}).encode(), "application/json")
                best, clicks = state["last"]
                path = write(name, pose_record(best["params"], clicks, picture, name, best["error"]))
                threading.Timer(0.5, lambda: os._exit(0)).start()
                return self._send(200, json.dumps({"msg": f"saved {path} - this page is done"}).encode(), "application/json")
            return self._send(404, b"{}", "application/json")

    url = f"http://127.0.0.1:{port}/?t={token}"
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"roto: the click page for {name} at {url}",
                      "next_action": f"open {url} - click the joints, Fit R6, flip limbs until the 3D preview is right, Save"}), flush=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    if os.environ.get("KIT_ROTO_NO_BROWSER") != "1":      # the kit buffers this command's output: open the page itself
        import webbrowser
        webbrowser.open(url)
    server.serve_forever()


def write(name, record):
    os.makedirs(POSES, exist_ok=True)
    if not NAME_OK.match(name):
        raise ValueError(f"pose name {name!r}: letters, digits, _ and - only")
    path = os.path.join(POSES, f"{name}.roto.json")
    json.dump(record, open(path, "w", encoding="utf-8", newline="\n"), indent=1)
    return path.replace(os.sep, "/")


def main(argv):
    if len(argv) < 2 or argv[0] not in ("fit", "serve"):
        print(json.dumps({"status": "fail", "summary": "roto: fit|serve <picture> --as <Pose> [--clicks clicks.json]",
                          "next_action": "lune run kit anim roto <picture> --as <Pose>"}))
        return 1
    picture = argv[1]
    name = argv[argv.index("--as") + 1] if "--as" in argv else os.path.splitext(os.path.basename(picture))[0]
    if argv[0] == "serve":
        serve(picture, name, int(argv[argv.index("--port") + 1]) if "--port" in argv else 8767)
        return 0
    data = json.load(open(argv[argv.index("--clicks") + 1], encoding="utf-8"))
    clicks = normalise({k: v for k, v in data["clicks"].items()}, data["width"], data["height"])
    best, alts = fit(clicks, data.get("flips"))
    path = write(name, pose_record(best["params"], clicks, picture, name, best["error"]))
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"roto {name}: R6 pose fitted, error {best['error'] * 100:.1f} % of the picture height, {len(alts)} depth alternate(s) -> {path}",
                      "next_action": f"use it: a strike key's arms_pose = {path} arms_pose (or open the page to flip limbs)", "pose": path}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

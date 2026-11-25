// gates_test.cjs - the recording gate's verdicts on synthetic frame curves (the player's own summarize(), sliced out of
// player.js by text): each case states what the gate MUST say. Exits 1 on any wrong verdict; prints one JSON line.
//   node kit/vfx/gates_test.cjs      (run by kit/test/python/test_vfx_gates.py inside kit verify)
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "player", "player.js"), "utf8");
const a = src.indexOf("export function summarize(");
let depth = 0, i = src.indexOf("{", a), end = i;
for (; end < src.length; end++) { if (src[end] === "{") depth++; else if (src[end] === "}") { depth--; if (depth === 0) break; } }
const code = src.slice(a, end + 1).replace("export function summarize", "function summarize") + "\nmodule.exports = summarize;";
const m = { exports: {} };
new Function("module", code)(m);
const summarize = m.exports;

const base = (t) => ({ t, hues: new Array(12).fill(0), hot: 0, mean: 30, coverage: 0.1, focal: 0.8, fpx: 200 });
const curve = (fn) => Array.from({ length: 60 }, (_, k) => Object.assign(base(k / 24), fn(k / 24)));
const check = (frames, preset, name) => summarize(frames, preset, "x", false).checks.find((c) => c.name === name);
// frames_on_screen is judged on the HERO view only: its cases run in "hero" (and one in "low", where it is not asked)
const checkIn = (view) => (frames, preset, name) => summarize(frames, preset, view, false).checks.find((c) => c.name === name);
const hit = { layers: [], hitstop: [], hits: [1.0] };
const framed = { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }],
  layers: [0, 0.07, 0.13, 0.19].map((d, k) => ({ kind: "impact", at: 1.0 + d, life: k === 3 ? 0.05 : 0.06 })) };
const cases = [
  // [label, frames, preset, check, must be ok]
  ["a snap on the hit", curve((t) => ({ mean: t < 1 ? 30 : 30 + 60 * Math.max(0, 1 - (t - 1.05) * 1.5) })), hit, "strike_snap", true],
  ["a slow ramp into the hit", curve((t) => ({ mean: 30 + 60 * Math.min(1, Math.max(0, (t - 0.65) / 0.45)) })), hit, "strike_snap", false],
  ["a glint, then a snap", curve((t) => ({ mean: t < 0.7 ? 30 : t < 0.85 ? 36 : t < 1 ? 30 : 30 + 60 * Math.max(0, 1 - (t - 1.05) * 1.5) })), hit, "strike_snap", true],
  // 2026-10-24: a long frame sequence ON the hit is the strike held on the clock - it must not count as a slow rise...
  ["a 0.29 s frame sequence on the hit, the scene bright after it", curve((t) => ({ mean: t < 1 ? 30 : t < 1.29 ? 200 : 30 + 60 * Math.max(0, 1 - (t - 1.29) * 1.5) })), framed, "strike_snap", true],
  // ...but a scene still ramping up after the frames is slow
  ["frames, then the scene ramps up for 0.5 s", curve((t) => ({ mean: t < 1 ? 30 : t < 1.29 ? 200 : 30 + 60 * Math.min(1, (t - 1.29) / 0.5) })), framed, "strike_snap", false],
  // the gate review's counter-examples (2026-10-24): frames must never buy a slow ramp, and a ramp INTO a framed hit counts
  ["a slow ramp INTO a framed hit", curve((t) => ({ mean: t < 0.6 ? 30 : t < 1 ? 30 + 60 * (t - 0.6) / 0.4 : t < 1.29 ? 200 : 90 })), framed, "strike_snap", false],
  ["a 0.01 s frame on the hit + a 0.2 s ramp", curve((t) => ({ mean: t < 1 ? 30 : 30 + 60 * Math.min(1, (t - 1) / 0.2) })),
    { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.1, span: 0.02 }], layers: [{ kind: "impact", at: 1.0, life: 0.01 }] }, "strike_snap", false],
  // the second review (2026-10-24): a framed hit's window stops at the NEXT hit, and frames that start a little before the
  // hit (frames_at_hits allows -0.06 s) are credited too - both clean snaps must pass
  ["a framed hit, then a second hit 0.5 s later, both snapping", curve((t) => ({ mean: t < 1 ? 30 : t < 1.29 ? 200 : t < 1.5 ? 90 : 150 })),
    { hits: [1.0, 1.5], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }], layers: framed.layers }, "strike_snap", true],
  ["frames starting 0.04 s before the hit, a clean snap", curve((t) => ({ mean: t < 0.96 ? 30 : t < 1.25 ? 200 : 30 + 60 * Math.max(0, 1 - (t - 1.25) * 1.5) })),
    { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }], layers: framed.layers.map((l) => ({ ...l, at: l.at - 0.04 })) }, "strike_snap", true],
  ["scattered clutter", curve(() => ({ focal: 0.2 })), hit, "focal", false],
  ["one clear shape", curve(() => ({ focal: 0.8 })), hit, "focal", true],
  // 2026-10-25 (the owner: "bad impact frames"): the frames' subject a speck fails; loved-like close-ups and no frames pass
  ["impact frames whose subject is a speck", curve((t) => (t >= 1 && t < 1.25 ? { sf: 0.05 } : {})), framed, "frames_fill", false],
  ["impact frames filled by their subject", curve((t) => (t >= 1 && t < 1.25 ? { sf: 0.7 } : {})), framed, "frames_fill", true],
  ["moonflower-like frames (owner 7/10, fill 0.33)", curve((t) => (t >= 1 && t < 1.25 ? { sf: 0.33 } : {})), framed, "frames_fill", true],
  ["no impact frames at all", curve(() => ({})), hit, "frames_fill", true],
  // 2026-10-25 (orrery): a fade-in to a plateau with a half-level wiggle is not a second climax - the curve never FALLS
  // after it; a real false climax (a build-up brighter than its fall, then the hit) still fails
  ["a fade-in plateau with a wiggle before a big hit", curve((t) => ({ mean: t < 0.4 ? 18 + 15 * t / 0.4 : t < 1.5 ? 33 + 0.5 * Math.sin(t * 40) : 33 + 60 * Math.max(0, 1 - (t - 1.55) * 1.5) })),
    { layers: [], hitstop: [], hits: [1.5] }, "one_peak_per_hit", true],
  // orrery's REAL low-view curve (recorded 2026-10-25): an 18.3 start, a 24-level plateau wiggling under half a level, the
  // hit to 48.8 - the wiggle at 1.03 was flagged as a second climax (it rose 6 above the START, it never falls)
  ["orrery's recorded low view", [[0.033,18.3],[0.033,18.3],[0.067,18.5],[0.1,18.8],[0.133,19],[0.133,19],[0.167,19.2],[0.2,19.4],[0.233,19.6],[0.233,19.6],[0.267,19.8],[0.3,20],[0.333,20.3],[0.333,20.3],[0.367,20.5],[0.4,20.7],[0.433,21.1],[0.433,21.1],[0.467,21.4],[0.5,21.6],[0.533,22],[0.533,22],[0.567,22.5],[0.6,22.7],[0.633,23.1],[0.633,23.1],[0.667,23.5],[0.7,24],[0.733,23.8],[0.733,23.8],[0.767,23.9],[0.8,24.1],[0.833,24.1],[0.833,24.1],[0.867,23.9],[0.9,23.8],[0.933,23.9],[0.933,23.9],[0.967,23.9],[1,24.2],[1.033,24.3],[1.033,24.3],[1.067,24],[1.1,24],[1.133,23.9],[1.133,23.9],[1.167,24],[1.2,24.1],[1.2,24.1],[1.233,24.2],[1.233,24.2],[1.267,24.1],[1.3,24],[1.3,24],[1.333,24],[1.333,24],[1.367,24],[1.4,23.9],[1.4,23.9],[1.433,24],[1.433,24],[1.467,24.1],[1.5,24.1],[1.5,24.1],[1.533,24.1],[1.533,24.1],[1.567,24.1],[1.6,24.2],[1.6,24.2],[1.633,24.2],[1.633,24.2],[1.667,24.2],[1.7,24.1],[1.7,24.1],[1.733,24.1],[1.733,24.1],[1.767,24.1],[1.8,24.2],[1.8,24.2],[1.833,24.1],[1.833,24.1],[1.867,25.6],[1.9,32.5],[1.9,33.3],[1.9,33.3],[1.9,33.3],[1.933,35.9],[1.933,35.9],[1.967,42.5],[2,48.8],[2.033,48],[2.033,48],[2.067,48.3],[2.1,48.1],[2.133,47.8],[2.133,47.8],[2.167,46.8],[2.2,45.9],[2.233,45],[2.233,45],[2.267,43.7],[2.3,42.3],[2.333,40.9],[2.333,40.9],[2.367,39.6],[2.4,38.6],[2.433,37.6],[2.433,37.6],[2.467,36.5],[2.5,35.6],[2.533,34.5],[2.533,34.5],[2.567,31.7],[2.6,30.8],[2.633,30.1],[2.633,30.1],[2.667,29.6],[2.7,29.3],[2.733,28.5],[2.733,28.5],[2.767,27.8],[2.8,25.3],[2.833,25.1],[2.833,25.1],[2.867,25],[2.9,24.9],[2.933,24.8],[2.933,24.8],[2.967,24.7],[3,24.5],[3.033,24.4],[3.033,24.4],[3.067,24.2],[3.1,24.1],[3.133,24],[3.133,24],[3.167,23.8],[3.2,23.7],[3.233,23.6],[3.233,23.6],[3.267,23.4],[3.3,23.3],[3.333,23.1],[3.333,23.1],[3.367,23],[3.4,22.8],[3.433,22.6],[3.433,22.6],[3.467,22.5],[3.5,22.3],[3.533,22.1],[3.533,22.1],[3.567,22],[3.6,21.9],[3.633,21.8],[3.633,21.8],[3.667,21.7],[3.7,21.6],[3.733,21.5],[3.733,21.5],[3.767,21.4],[3.8,21.3],[3.833,21.2],[3.833,21.2],[3.867,21],[3.9,20.9],[3.933,20.8],[3.933,20.8],[3.967,20.6],[4,20.5],[4.033,20.4],[4.033,20.4],[4.067,20.3],[4.1,20.2],[4.133,20.1],[4.133,20.1],[4.167,20],[4.2,19.9],[4.233,19.8],[4.233,19.8],[4.267,19.7],[4.3,19.6],[4.333,19.4],[4.333,19.4],[4.367,19.3],[4.4,19.2],[4.433,19],[4.433,19],[4.467,18.9],[4.5,18.8],[4.533,18.7],[4.533,18.7],[4.567,18.6],[4.6,18.4],[4.633,18.3],[4.633,18.3],[4.667,18.3],[4.7,18.2],[4.733,18],[4.733,18],[4.767,18],[4.8,18]].map(([t, mean]) => Object.assign(base(t), { mean })),
    { layers: [], hitstop: [{ at: 1.9, hold: 0.12, span: 0.05 }], hits: [1.9] }, "one_peak_per_hit", true],
  // the review's curves (2026-10-25): a late flare at the clip's end must still fail; a plateau wiggle, a
  // wind-up dip, then the hit must pass
  ["a second flare at the very end of the clip", curve((t) => ({ mean: t < 0.5 ? 25 : t < 0.6 ? 95 : t < 2.15 ? Math.max(25, 95 - 140 * (t - 0.6)) : t < 2.25 ? 25 + 45 * (t - 2.15) / 0.1 : 70 - 25 * (t - 2.25) })),
    { layers: [], hitstop: [], hits: [0.5] }, "one_peak_per_hit", false],
  // the KNOWN LIMIT, by choice (a held level is not a climax): a build-up that sags 8 % and holds into the hit passes
  ["a build-up to 60 that only sags to 52, then the hit to 95", curve((t) => ({ mean: t < 0.6 ? 20 + 40 * t / 0.6 : t < 0.8 ? 60 - 40 * (t - 0.6) : t < 1.6 ? 52 : 52 + 43 * Math.min(1, (t - 1.6) / 0.05) * Math.max(0.5, 1 - (t - 1.7)) })),
    { layers: [], hitstop: [], hits: [1.6] }, "one_peak_per_hit", true],
  ["a plateau wiggle, a wind-up dip, then the hit", curve((t) => ({ mean: t < 0.3 ? 20 + 30 * t / 0.3 : t < 1.2 ? 50 + 0.5 * Math.sin(t * 30) : t < 1.5 ? 35 : 35 + 60 * Math.min(1, (t - 1.5) / 0.05) * Math.max(0.5, 1 - (t - 1.6)) })),
    { layers: [], hitstop: [], hits: [1.5] }, "one_peak_per_hit", true],
  ["a build-up that climaxes and falls before the hit", curve((t) => ({ mean: t < 0.6 ? 20 + 40 * t / 0.6 : t < 1.0 ? 60 - 35 * (t - 0.6) / 0.4 : t < 1.5 ? 25 : 25 + 70 * Math.max(0, 1 - (t - 1.55) * 1.5) })),
    { layers: [], hitstop: [], hits: [1.5] }, "one_peak_per_hit", false],
  // 2026-10-25 (the owner: "not everything needs impact frame"): a hit with no frames passes; frames off any hit fail
  ["a hit with no impact frames", curve(() => ({})), { layers: [], hitstop: [{ at: 1.0, hold: 0.12, span: 0.05 }], hits: [1.0] }, "frames_at_hits", true],
  ["a frame sequence 0.5 s off its hit", curve(() => ({})), { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }],
    layers: framed.layers.map((l) => ({ ...l, style: "frame", at: l.at + 0.5 })) }, "frames_at_hits", false],
  ["a frame sequence on its hit", curve(() => ({})), { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }],
    layers: framed.layers.map((l) => ({ ...l, style: "frame" })) }, "frames_at_hits", true],
  // 2026-11-10 (the owner's "bad impact frames" on seam / sandfall / quicksilver / noctiluca): frames that RE-FRAME the
  // shot over a strike the viewer never saw fail; over a strike on screen, or drawn from the live shot, they pass
  ["re-framed frames over a speck (seam: 0.008 of the frame)", curve((t) => ({ fpx: t < 1 ? 18 : 200 })),
    { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }], layers: framed.layers.map((l, k) => ({ ...l, style: "frame", camera: ["cut", "low", "wide", "cut"][k] })) },
    "frames_on_screen", false, "hero"],
  ["frames with no camera (the player's closeup) over a speck", curve((t) => ({ fpx: t < 1 ? 18 : 200 })),
    { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }], layers: framed.layers.map((l) => ({ ...l, style: "frame" })) },
    "frames_on_screen", false, "hero"],
  ["re-framed frames over a strike on screen (starblade: 0.13-0.43)", curve((t) => ({ fpx: t < 1 ? 300 : 900 })),
    { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }], layers: framed.layers.map((l) => ({ ...l, style: "frame", camera: "low" })) },
    "frames_on_screen", true, "hero"],
  ["a strike seen 0.8 s before the frames (a wind-up dip right before them)", curve((t) => ({ fpx: t < 0.3 ? 0 : t < 0.5 ? 300 : t < 1 ? 20 : 900 })),
    { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }], layers: framed.layers.map((l) => ({ ...l, style: "frame", camera: "wide" })) },
    "frames_on_screen", true, "hero"],
  ["live-view frames (camera none) over a speck", curve((t) => ({ fpx: t < 1 ? 0 : 200 })),
    { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }], layers: framed.layers.map((l) => ({ ...l, style: "frame", camera: "none" })) },
    "frames_on_screen", true, "hero"],
  ["no impact frames, a speck of a hit", curve((t) => ({ fpx: t < 1 ? 5 : 20 })), hit, "frames_on_screen", true, "hero"],
  ["re-framed frames over a speck, judged from the low view (hero only: not asked)", curve((t) => ({ fpx: t < 1 ? 18 : 200 })),
    { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }], layers: framed.layers.map((l) => ({ ...l, style: "frame", camera: "cut" })) },
    "frames_on_screen", true, "low"],
  // the review (2026-11-10): a DARK strike (a void, ink) filling the shot is on screen though no pixel is brighter
  ["re-framed frames over a dark strike filling the shot (dpx)", curve((t) => ({ fpx: 0, dpx: t < 1 ? 700 : 900 })),
    { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }], layers: framed.layers.map((l) => ({ ...l, style: "frame", camera: "closeup" })) },
    "frames_on_screen", true, "hero"],
  // ...and a booth with no hero view is asked in its first view
  ["re-framed frames over a speck, a side-only booth (asked in side)", curve((t) => ({ fpx: t < 1 ? 18 : 200 })),
    { hits: [1.0], hitstop: [{ at: 1.0, hold: 0.5, span: 0.3 }], booth: { views: ["side"] }, layers: framed.layers.map((l) => ({ ...l, style: "frame", camera: "cut" })) },
    "frames_on_screen", false, "side"],
];
const results = cases.map(([label, frames, preset, name, want, view]) => {
  const c = (view ? checkIn(view) : check)(frames, preset, name);
  return { label, check: name, want, got: c ? c.ok : null, value: c ? c.value : null, ok: c ? c.ok === want : false };
});
const bad = results.filter((r) => !r.ok);
console.log(JSON.stringify({ status: bad.length ? "fail" : "pass", ran: results.length, failed: bad }));
process.exit(bad.length ? 1 : 0);

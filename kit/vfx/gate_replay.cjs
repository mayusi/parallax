// gate_replay.cjs - the recording gate (player.js summarize(), sliced out by text as gates_test.cjs does) re-run on a
// STORED recording: its metrics.json (views -> per-frame metrics) + the bundle it was recorded from (the library's
// expanded.json: preset + views). The owner's real bad examples stay bad examples forever (kit selftest): a gate that
// passes the very recording the owner rejected is a gate that lies (2026-11-10: seam passed 10 of 10 recording checks).
//   node kit/vfx/gate_replay.cjs <metrics.json> <expanded.json> [--checks a,b] [--views hero,low]
// Prints one JSON verdict: "fail" when any asked check fails in any asked view (default: every check, every view).
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

const say = (status, summary, next_action, extra) => {
  console.log(JSON.stringify({ schema: 1, status, summary, next_action, ...(extra || {}) }));
  process.exit(status === "pass" ? 0 : 1);
};
const args = process.argv.slice(2);
const flag = (k) => { const j = args.indexOf(k); return j >= 0 ? args[j + 1] : null; };
const [metricsPath, bundlePath] = args.filter((x, j) => !x.startsWith("--") && !(j > 0 && args[j - 1].startsWith("--")));
if (!metricsPath || !bundlePath) say("fail", "gate replay: needs <metrics.json> <expanded.json>", "node kit/vfx/gate_replay.cjs <metrics.json> <expanded.json> [--checks a,b] [--views hero]");
let metrics, bundle;
try { metrics = JSON.parse(fs.readFileSync(metricsPath, "utf8")); bundle = JSON.parse(fs.readFileSync(bundlePath, "utf8")); }
catch (e) { say("fail", `gate replay: cannot read ${metricsPath} / ${bundlePath}: ${e.message}`, "pass a stored metrics.json and the expanded.json it was recorded from"); }
const preset = bundle.preset || bundle;
const viewDefs = bundle.views || {};
const wantChecks = flag("--checks") ? flag("--checks").split(",") : null;
const wantViews = flag("--views") ? flag("--views").split(",") : null;
const name = metrics.name || preset.name || path.basename(path.dirname(metricsPath));
const views = Object.entries(metrics.views || {}).filter(([v]) => !wantViews || wantViews.includes(v));
if (!views.length) say("fail", `gate replay ${name}: no recorded view ${wantViews ? wantViews.join(", ") : ""} in ${metricsPath}`, "record the effect first: lune run kit vfx play <name> --record");
const failed = [], asked = [];
for (const [v, rec] of views) {
  const moving = !!(viewDefs[v] && viewDefs[v].path);
  const res = summarize(rec.frames || [], preset, v, moving);
  for (const c of res.checks) {
    if (wantChecks && !wantChecks.includes(c.name)) continue;
    asked.push(`${v}.${c.name}`);
    if (!c.ok) failed.push(`${v}.${c.name} ${JSON.stringify(c.value)} (${c.limit})`);
  }
}
if (wantChecks) for (const c of wantChecks) if (!asked.some((x) => x.endsWith(`.${c}`))) say("fail", `gate replay ${name}: the gate has no check "${c}"`, "name a check summarize() makes (kit/vfx/player/player.js)");
if (failed.length) say("fail", `gate replay ${name}: ${failed.length} check(s) fail on the stored recording: ${failed.join("; ")}`, "the recording breaks a gate check: fix the effect, never the gate", { failed });
say("pass", `gate replay ${name}: ${asked.length} check(s) hold on the stored recording (${views.map(([v]) => v).join(", ")})`, "none", { asked });

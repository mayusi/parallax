"""Put each candidate's kit warnings ON the pick sheet, under its card (the owner, 2026-11-08: "Act on the warnings").

On 2026-11-04 all 16 candidates the owner was shown carried the kit's own warnings that a limb moved less than in the
loved clips ("Left Arm rot_range 22.9 < loved p10 30.73", "support_leg slide_p95 0.39 < loved p10 0.661"), on exactly
the limbs the owner then rejected ("stilts", "arm-only swing"). The warnings lived only in the round's manifest; nobody
saw them. This step reads them from assets/animations/candidates/<Name>/round_K.json and writes them into
build/candidates/<Name>/round_K/picks.html (the page kit/anim/proc_picks.py builds): one block per card plus a line at
the top, then the round's CHECKS from the owner's words (kit/checks/checks.py, kit/knowledge/vault/anim/checks.json:
"cousins", "stilts" ...), each with its status - a proposed check reports, it never blocks. It changes no candidate
and no gate. Running it again replaces its own blocks.

usage: python kit/anim/pick_warnings.py <Name> [--round K]   -> one JSON line {"cards", "warned", "checks_failed", "page"}
"""

import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFESTS = os.path.join("assets", "animations", "candidates")
MARK = "<!-- kit warnings -->"
STYLE = (
    f"{MARK}<style>.kitwarn{{margin-top:6px;font-size:12px;color:#a8321f;border-left:3px solid #d9542b;"
    "padding-left:6px}} @media (prefers-color-scheme:dark){{.kitwarn{{color:#ff9f86;border-color:#ff7b5c}}}}"
    ".kitwarn b{{font-weight:600}}</style>"
).replace("{{", "{").replace("}}", "}")


def strip_old(doc):
    doc = doc.replace(STYLE, "")
    doc = re.sub(r'<div class="kitwarn"[^>]*>.*?</div>', "", doc, flags=re.S)
    doc = re.sub(r'<div class="kitchecks">.*?</div>', "", doc, flags=re.S)
    return re.sub(r'<p class="kitwarn-top">.*?</p>', "", doc, flags=re.S)


def checks_block(name, rnd):
    """the round's checks from the owner's words, as a block for the top of the sheet ("", [] when there are none).
    They run in their OWN process (kit/checks/checks.py): one of them loads a GPU model, and a crash there must never
    lose the sheet or its warnings - the sheet is written before they run."""
    import subprocess  # noqa: PLC0415

    tool = os.path.normpath(os.path.join(HERE, "..", "checks", "checks.py"))
    why = ""
    try:
        p = subprocess.run([sys.executable, tool, "run", "anim", f"{name}/round_{rnd}"], capture_output=True,
                           text=True, timeout=600, check=False)
        last = (p.stdout or "").strip().splitlines()[-1:] or ["{}"]
        res = json.loads(last[0])
        if "error" in res or p.returncode != 0:
            why = res.get("error") or (p.stderr or "")[-120:] or f"exit {p.returncode}"
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        why, res = str(e), {}
    if why:
        esc = html.escape(str(why)[:160])
        return f"<div class=\"kitchecks\"><b>Checks from the owner&#39;s words:</b> not run ({esc})</div>", []
    if not res.get("lines"):
        return "", []
    items = "".join(
        f"<li>{'<b>' if ': FAIL' in ln else ''}{html.escape(ln.strip())}{'</b>' if ': FAIL' in ln else ''}</li>"
        for ln in res["lines"])
    head = "<b>Checks from the owner&#39;s words</b> (a proposed check reports, it never blocks):"
    return f"<div class=\"kitchecks\">{head}<ul>{items}</ul></div>", res["failed"]


def annotate(doc, cards):
    doc = strip_old(doc)
    warned = present = 0
    for c in cards:
        cid = html.escape(str(c.get("id", "")))
        head = f'<figure class="card" data-id="{cid}"'
        at = doc.find(head)
        if at < 0:
            continue  # dropped by proc_picks (not faithful on the rig): not on the sheet, not counted
        present += 1
        warnings = [str(w) for w in (c.get("warnings") or [])]
        if not warnings:
            continue
        block = (
            '<div class="kitwarn"><b>Kit warnings (outside the loved range):</b> '
            + "; ".join(html.escape(w) for w in warnings)
            + "</div>"
        )
        cap = doc.find("</figcaption>", at)
        if cap < 0:
            continue
        doc = doc[:cap] + block + doc[cap:]
        warned += 1
    top = (
        f'<p class="kitwarn-top"><b>{warned} of {present} candidates on this sheet carry kit warnings</b> '
        "(a limb or the blade moving outside the loved clips' range). On 2026-11-04 the owner rejected candidates "
        "with these warnings as &quot;stilts&quot; and &quot;arm-only swing&quot;.</p>"
        if warned
        else ""
    )
    doc = doc.replace("</head>", STYLE + "</head>", 1)
    if top:
        doc = re.sub(r"(<h1>.*?</h1>)", lambda m: m.group(1) + top, doc, count=1, flags=re.S)
    return doc, warned, present


def main(argv):
    if len(argv) < 2:
        print(json.dumps({"error": "usage: pick_warnings.py <Name> [--round K]"}))
        return 2
    name = argv[1]
    rnd = int(argv[argv.index("--round") + 1]) if "--round" in argv else 0
    manifest = os.path.join(MANIFESTS, name, f"round_{rnd}.json")
    page = os.path.join("build", "candidates", name, f"round_{rnd}", "picks.html")
    if not os.path.isfile(manifest) or not os.path.isfile(page):
        print(json.dumps({"error": f"needs {manifest} and {page} (run kit anim picks first)"}))
        return 1
    with open(manifest, encoding="utf-8") as f:
        cards = json.load(f).get("candidates") or []
    with open(page, encoding="utf-8") as f:
        doc = f.read()
    doc, warned, present = annotate(doc, cards)
    # the warnings are written FIRST: whatever happens to the checks, the sheet keeps them
    with open(page, "w", encoding="utf-8", newline="") as f:
        f.write(doc)
    block, failed = checks_block(name, rnd)
    if block:
        if '<p class="kitwarn-top">' in doc:
            doc = re.sub(r'(<p class="kitwarn-top">.*?</p>)', lambda m: m.group(1) + block, doc, count=1, flags=re.S)
        else:
            doc = re.sub(r"(<h1>.*?</h1>)", lambda m: m.group(1) + block, doc, count=1, flags=re.S)
        with open(page, "w", encoding="utf-8", newline="") as f:
            f.write(doc)
    # the kit reads a step's verdict from its "status" (Run.content): without one every sheet - a clean one too - was
    # reported as a failed step (2026-11-10: Roundhouse round 6, 0 of 7 warned, no check failing, "failed")
    print(json.dumps({"status": "fail" if failed else "pass",
                      "summary": f"{warned} of {present} card(s) carry kit warnings" + (f"; failing: {', '.join(failed)}" if failed else ""),
                      "next_action": "show the failing checks with the piece (a proposed check reports, it never blocks)" if failed
                      else "none - proceed",
                      "cards": present, "warned": warned, "checks_failed": failed, "page": page.replace(os.sep, "/")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

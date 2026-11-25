"""patent.py — a PATENT as modelling references. A DESIGN patent draws the product in clean orthographic line art
(the views photos never give: top, front, back); a UTILITY patent draws the MECHANISM — sections and part-by-part
figures with every pivot and spring in place (Browning's 1911: US 984,519). Fetches the official PDF from the USPTO,
splits every drawing sheet into its figures, and saves each as a picture you can trace.

    python kit/refs/patent.py D885516 [--out build/refs/patents]      (design: D + digits)
    python kit/refs/patent.py 984519                                   (utility: digits; US 984,519 works too)

Source: image-ppubs.uspto.gov (the USPTO's own public PDF service: free, no login). US patents are public records;
the figures keep "US <number> (USPTO)" as their source. Find a product's design patents by its maker on any patent
search, then pass the number (D + digits). Pages come out of the PDF as they were scanned (pypdf, BSD: no rendering);
figures are found as the big clusters of ink on a sheet (labels and page furniture are small and dropped).
"""

import json
import os
import re
import sys
import time
import urllib.request

import numpy as np

UA = os.environ.get("KIT_REFS_UA") or "roblox-kit-refs/1.0 (local reference search for a Roblox content kit)"


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra},
                     ensure_ascii=False))
    return 0 if status == "pass" else 1


def number_of(text):
    """'USD885516S', 'D885,516', 'd885516' -> 'D885516' (design patents); 'US 984,519', '984519', 'US0984519A' ->
    '0984519' (utility patents: the USPTO's print service wants 7 digits, zero-padded); None when it is neither"""
    t = re.sub(r"[^0-9A-Za-z]", "", text or "").upper()
    m = re.fullmatch(r"(?:US)?(D)0*(\d{5,7})(?:S\d?)?", t)
    if m:
        return f"D{m.group(2)}"
    m = re.fullmatch(r"(?:US)?0*(\d{4,7})(?:[AB]\d?)?", t)  # (up to 7 digits: patents before June 2018; the 8-digit
    # ones since are not supported yet — the print service's form for them is unverified)
    return m.group(1).zfill(7) if m else None


def figures(page, min_share=0.004, join=18):
    """split a scanned drawing sheet (bool ink mask, True = ink) into figures: ink grown by `join` px so a figure's
    strokes merge, connected clusters, kept when big enough -> list of (x0, y0, x1, y1) boxes, top-left first"""
    from scipy.ndimage import binary_dilation, find_objects, label  # noqa: PLC0415

    h, w = page.shape
    margin = int(0.04 * h)
    ink = page.copy()
    ink[:margin] = False  # the page header (patent number, sheet n of m) is not a figure
    grown = binary_dilation(ink, iterations=join)
    lab, n = label(grown)
    boxes = []
    for k, sl in enumerate(find_objects(lab), 1):
        if sl is None:
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        inked = int(ink[sl][lab[sl] == k].sum())
        if inked < min_share * ink.sum() or (x1 - x0) < 0.08 * w or (y1 - y0) < 0.05 * h:
            continue  # a label ("FIG. 3"), a reference numeral, a speck
        boxes.append((max(0, x0 - 8), max(0, y0 - 8), min(w, x1 + 8), min(h, y1 + 8)))
    return sorted(boxes, key=lambda b: (round(b[1] / (0.1 * h)), b[0]))


def main(argv):
    if not argv:
        return emit("fail", "refs patent: needs a patent number", "lune run kit refs patent D885516   (or a utility "
                    "patent's digits: 984519)")
    num = number_of(argv[0])
    if not num:
        return emit("fail", f"refs patent: '{argv[0]}' is not a patent number (D + digits, or a utility patent's "
                    "digits)", "design patents draw the product in orthographic views (D885516); utility patents its "
                    "mechanism (984519)")
    out = os.path.join(argv[argv.index("--out") + 1] if "--out" in argv else os.path.join("build", "refs", "patents"), num)
    os.makedirs(out, exist_ok=True)
    pdf = os.path.join(out, f"{num}.pdf")
    if not os.path.isfile(pdf):
        req = urllib.request.Request(f"https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/{num}",
                                     headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read(40 * 1024 * 1024)
        except Exception as e:  # noqa: BLE001
            return emit("fail", f"refs patent: {num} could not be fetched ({e})", "check the number on a patent search")
        if not data.startswith(b"%PDF"):
            return emit("fail", f"refs patent: the USPTO returned no PDF for {num}", "check the number (design patents: D + digits)")
        with open(pdf, "wb") as fh:
            fh.write(data)
    from PIL import Image  # noqa: PLC0415
    from pypdf import PdfReader  # noqa: PLC0415

    reader = PdfReader(pdf)
    saved = []
    for pi, page in enumerate(reader.pages):
        for img in page.images:
            sheet = img.image.convert("L")
            ink = np.asarray(sheet) < 128
            if ink.mean() < 0.002:
                continue  # blank
            boxes = figures(ink)
            # the first page of a design patent is mostly text + one figure; later pages are drawing sheets
            for bi, (x0, y0, x1, y1) in enumerate(boxes):
                fig = sheet.crop((x0, y0, x1, y1))
                name = f"{num}_p{pi + 1}_fig{bi + 1}.png"
                fig.save(os.path.join(out, name))
                with open(os.path.join(out, name + ".json"), "w", encoding="utf-8") as fh:
                    json.dump({"source": "uspto", "id": num, "title": f"US {num} — page {pi + 1}, figure {bi + 1}",
                               "creator": "USPTO (patent drawing)", "license": "pdm",
                               "license_version": "Public record (US patent)", "license_url": "",
                               "page": f"https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/{num}",
                               "url": "", "width": fig.width, "height": fig.height, "file": name,
                               "retrieved": time.strftime("%Y-%m-%d")}, fh, indent=1)
                saved.append(name)
    if not saved:
        return emit("fail", f"refs patent: {num} has no drawings the splitter could find", f"look at {pdf} yourself")
    return emit("pass", f"refs patent: {num} -> {len(saved)} figure(s) from {len(reader.pages)} page(s) in {out}",
                f"rank them (which view is which): lune run kit refs rank {out} --what \"<the product>\"",
                out=out.replace("\\", "/"), figures=saved)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

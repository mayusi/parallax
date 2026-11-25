"""server.py — `kit rate serve <round>`: the owner grading page on http://127.0.0.1:8796 (local only).
GET  /                         the page (kit/grading/page)
GET  /round/...                the round's files (build/grading/<round>: models, refs)
GET  /api/round                round.json (the models, their references)
GET  /api/ratings              {asset: {score 0-10, words, at}}
POST /api/rate {asset, score, words}  -> build/grading/<round>/ratings.json (score 0-10 in halves, words <= 800 chars)
Binds 127.0.0.1 only; a POST from another origin is refused."""
import json
import os
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PAGE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(PAGE)))
PORT = 8796


def make_handler(rnd):
    root = os.path.join(REPO, "build", "grading", rnd)

    def load(name):
        try:
            with open(os.path.join(root, name), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=PAGE, **k)

        def translate_path(self, path):
            if path.startswith("/round/"):   # (the round's own files, never anything above it)
                rel = os.path.normpath(path[len("/round/"):].split("?")[0]).lstrip("\\/")
                full = os.path.abspath(os.path.join(root, rel))
                return full if full.startswith(os.path.abspath(root) + os.sep) else os.path.join(root, "_none_")
            return super().translate_path(path)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            """DNS rebinding: a page on another name resolving to 127.0.0.1 must not read or write the round — only
            requests addressed to 127.0.0.1:<port> / localhost:<port> are served"""
            port = self.server.server_address[1]
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "host"})
            if self.path.startswith("/api/round"):
                return self._json(200, load("round.json"))
            if self.path.startswith("/api/ratings"):
                return self._json(200, {k: v for k, v in load("ratings.json").items() if not k.startswith("_")})
            return super().do_GET()

        def do_POST(self):
            if not self._host_ok():
                return self._json(403, {"error": "host"})
            if not self.path.startswith("/api/rate"):
                return self._json(404, {"error": "not found"})
            port = self.server.server_address[1]
            if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self._json(403, {"error": "origin"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 6000:
                return self._json(413, {"error": "too large"})
            try:
                req = json.loads(self.rfile.read(n) or b"{}")
                asset = str(req.get("asset") or "")
                if asset not in {i.get("asset") for i in load("round.json").get("items") or []}:
                    raise ValueError("not in this round")
                score = req.get("score")
                if score is not None:
                    score = round(float(score) * 2) / 2
                    if not 0 <= score <= 10:
                        raise ValueError("score 0-10")
                words = str(req.get("words") or "")[:800]
            except (ValueError, TypeError) as e:
                return self._json(400, {"error": str(e)})
            data = load("ratings.json")
            data[asset] = {"score": score, "words": words, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            with open(os.path.join(root, "ratings.json"), "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
            return self._json(200, {"ok": True, "saved": data[asset]})

        def log_message(self, *a):
            pass

    return H, root


if __name__ == "__main__":
    rnd = sys.argv[1] if len(sys.argv) > 1 else ""
    H, root = make_handler(rnd)
    if not os.path.isfile(os.path.join(root, "round.json")):
        sys.exit(f"no round {rnd}: lune run kit rate make {rnd or '<round>'} <asset> ...")
    print(f"owner grading page ({rnd}): http://127.0.0.1:{PORT}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()

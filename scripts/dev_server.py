"""Local dev server: static files + GET /api/sensors (same code as the Vercel function).

Usage: python3 scripts/dev_server.py [port]   (default 8000)
If the sources are unreachable, /api/sensors answers with data/sensors_snapshot.json.
"""
import json
import pathlib
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from sensors import collect  # noqa: E402


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] in ("/api/sensors", "/api/sensors.py"):
            try:
                data = collect()
                if not data["sensors"]:
                    raise RuntimeError("no sensors")
            except Exception:  # noqa: BLE001
                data = json.loads((ROOT / "data" / "sensors_snapshot.json").read_text())
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(ROOT))).serve_forever()

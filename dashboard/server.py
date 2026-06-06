"""Serveur local du tableau de bord MemBridge.

Sert l'interface et expose une API qui lance le benchmark à la demande :
    GET /            -> dashboard (index.html)
    GET /api/run?turns=N -> exécute run_benchmark(N) et renvoie le rapport JSON

Aucune dépendance externe (bibliothèque standard uniquement).

Lancement :
    python dashboard/server.py            # puis ouvrir http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent.parent
# Rendre le code source importable même sans installation éditable.
for p in (ROOT / "src", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from benchmark.harness import REPORT_PATH, _write_report, run_benchmark  # noqa: E402

DASHBOARD_DIR = Path(__file__).parent
LIVE_PATH = ROOT / "benchmark" / "results" / "live.json"
PORT = 8000


class DashboardHandler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, content_type: str = "application/json") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 (signature imposée par http.server)
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            html = (DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")
            self._send(200, html, "text/html; charset=utf-8")
            return

        if parsed.path in ("/live", "/live.html"):
            html = (DASHBOARD_DIR / "live.html").read_text(encoding="utf-8")
            self._send(200, html, "text/html; charset=utf-8")
            return

        if parsed.path == "/api/live":
            if LIVE_PATH.exists():
                self._send(200, LIVE_PATH.read_text(encoding="utf-8"))
            else:
                self._send(200, json.dumps({"empty": True}))
            return

        if parsed.path == "/api/live/reset":
            if LIVE_PATH.exists():
                LIVE_PATH.unlink()
            self._send(200, json.dumps({"reset": True}))
            return

        if parsed.path == "/api/report":
            if REPORT_PATH.exists():
                self._send(200, REPORT_PATH.read_text(encoding="utf-8"))
            else:
                self._send(200, json.dumps({"empty": True}))
            return

        if parsed.path == "/api/run":
            params = parse_qs(parsed.query)
            try:
                turns = int(params.get("turns", ["50"])[0])
            except ValueError:
                turns = 50
            turns = max(2, min(turns, 300))

            started = time.time()
            report = run_benchmark(turn_count=turns)
            report["elapsed_sec"] = round(time.time() - started, 2)
            _write_report(report)
            self._send(200, json.dumps(report, ensure_ascii=False))
            return

        self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, fmt: str, *args) -> None:  # silence les logs verbeux
        return


def main() -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), DashboardHandler)
    print(f"Tableau de bord MemBridge → http://127.0.0.1:{PORT}")
    print("Ctrl+C pour arrêter.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
        httpd.server_close()


if __name__ == "__main__":
    main()

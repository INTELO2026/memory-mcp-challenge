"""Serveur HTTP léger pour le dashboard MemBridge."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent
DASHBOARD_DIR = ROOT
_tools = MemoryTools()


class DashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_file(DASHBOARD_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/stats":
            self._send_json(_tools.memory_stats())
        elif path == "/memories":
            entries = _tools.store.list_active()
            self._send_json(
                {
                    "memories": [
                        {
                            "id": e.id,
                            "content": e.content[:120],
                            "tags": e.tags,
                            "session": e.session,
                            "turn": e.turn,
                            "importance": e.importance,
                            "retention_score": e.retention_score,
                            "stability": e.stability,
                            "created_at": e.created_at.isoformat() if e.created_at else None,
                        }
                        for e in entries[:50]
                    ]
                }
            )
        elif path == "/graph":
            self._send_json(_tools.store.graph_data())
        elif path == "/retention":
            self._send_json({"curves": _tools.store.retention_curves()})
        elif path == "/benchmark":
            report_path = ROOT.parent / "benchmark" / "results" / "report.json"
            if report_path.exists():
                data = json.loads(report_path.read_text(encoding="utf-8"))
                self._send_json(data)
            else:
                from benchmark.harness import run_benchmark, save_report

                report = run_benchmark()
                save_report(report)
                self._send_json(report)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/reset":
            _tools.reset()
            from memory_mcp.stats import reset_stats

            reset_stats()
            self._send_json({"reset": True})
        else:
            self.send_error(404)

    def log_message(self, format: str, *args) -> None:
        pass


def main(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = HTTPServer((host, port), DashboardHandler)
    print(f"MemBridge dashboard -> http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

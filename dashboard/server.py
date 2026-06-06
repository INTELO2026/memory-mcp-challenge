"""Serveur dashboard + API live conversation (MCP en temps reel)."""

from __future__ import annotations

import argparse
import json
import mimetypes
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from demo.live_engine import MANAGER
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).resolve().parent.parent
MCP = MemoryTools()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        if str(args[1]) != "200":
            super().log_message(format, *args)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/live/sessions/") and path.endswith("/state"):
            session_id = path.split("/")[4]
            live = MANAGER.get(session_id)
            if live is None:
                _json_response(self, 404, {"error": "session not found"})
                return
            _json_response(self, 200, live.to_dict())
            return

        if path == "/api/live/traps":
            from benchmark.traps import TRAP_QUESTIONS

            _json_response(
                self,
                200,
                {"traps": [{"query": q, "expected": e} for q, e in TRAP_QUESTIONS]},
            )
            return

        self._serve_static(path)

    def do_POST(self) -> None:
        global MCP
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "invalid json"})
            return

        if path == "/api/live/sessions":
            live = MANAGER.create(
                session_name=body.get("session"),
                target_turns=int(body.get("turns", 50)),
                offline=body.get("offline", True),
            )
            _json_response(self, 201, live.to_dict())
            return

        parts = path.strip("/").split("/")
        if len(parts) >= 4 and parts[0] == "api" and parts[1] == "live" and parts[2] == "sessions":
            session_id = parts[3]
            action = parts[4] if len(parts) > 4 else ""

            if action == "step":
                try:
                    event = MANAGER.step(session_id)
                    _json_response(self, 200, event)
                except KeyError:
                    _json_response(self, 404, {"error": "session not found"})
                return

            if action == "trap":
                query = body.get("query", "")
                if not query:
                    _json_response(self, 400, {"error": "query required"})
                    return
                try:
                    result = MANAGER.search_trap(session_id, query)
                    _json_response(self, 200, result)
                except KeyError:
                    _json_response(self, 404, {"error": "session not found"})
                return

            if action == "traps":
                try:
                    quality = MANAGER.evaluate_traps(session_id)
                    _json_response(self, 200, quality)
                except KeyError:
                    _json_response(self, 404, {"error": "session not found"})
                return

        if path == "/api/mcp/store":
            result = MCP.memory_store(
                content=body.get("content", ""),
                tags=body.get("tags"),
                session=body.get("session", "console"),
                turn=int(body.get("turn", 0)),
                importance=body.get("importance"),
            )
            _json_response(self, 200, result)
            return

        if path == "/api/mcp/search":
            result = MCP.memory_search(
                query=body.get("query", ""),
                top_k=int(body.get("top_k", 5)),
                session=body.get("session"),
                tag=body.get("tag"),
                min_importance=int(body.get("min_importance", 0)),
                exclude_tags=body.get("exclude_tags"),
            )
            _json_response(self, 200, result)
            return

        if path == "/api/mcp/summarize":
            result = MCP.memory_summarize(
                session=body.get("session", "console"),
                max_tokens=body.get("max_tokens"),
                use_llm=body.get("use_llm", False),
            )
            _json_response(self, 200, result)
            return

        if path == "/api/mcp/stats":
            result = MCP.memory_stats(session=body.get("session"))
            _json_response(self, 200, result)
            return

        if path == "/api/mcp/reset":
            from memory_mcp.stats import reset_stats
            from memory_mcp.storage import MemoryStore

            reset_stats()
            MCP = MemoryTools(store=MemoryStore())
            _json_response(self, 200, {"reset": True})
            return

        _json_response(self, 404, {"error": "not found"})

    def _serve_static(self, path: str) -> None:
        if path == "/":
            path = "/dashboard/index.html"
        file_path = (ROOT / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(ROOT.resolve())):
            self.send_error(403)
            return
        if not file_path.is_file():
            self.send_error(404)
            return
        content = file_path.read_bytes()
        mime, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serveur dashboard MemBridge + API live")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    url = f"http://localhost:{args.port}/dashboard/live.html"
    server = ThreadingHTTPServer(("", args.port), DashboardHandler)
    print(f"MemBridge -> {url}")
    print("API live : POST /api/live/sessions puis POST .../step")
    print("Arret : Ctrl+C")
    if args.open:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()

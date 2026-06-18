from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .supervisor_agent import SupervisorAgent


HOST = "127.0.0.1"
PORT = 8005
supervisor = SupervisorAgent()


class AgentRequestHandler(BaseHTTPRequestHandler):
    server_version = "GrafanaAgentHTTP/1.0"

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json({"ok": True, "service": "grafana-monitoring-agent", "port": PORT})
            return
        self._send_json({"ok": False, "error": "Not found"}, status=404)

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return

        try:
            payload = self._read_json()
            message = str(payload.get("message", ""))
            response = supervisor.chat(message)
            self._send_json(
                {
                    "ok": True,
                    "answer": response.answer,
                    "route": response.route,
                    "task": response.task,
                    "raw": response.raw,
                }
            )
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), AgentRequestHandler)
    print(f"Backend listening on http://{HOST}:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()


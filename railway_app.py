from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


SERVICE_NAME = "hft-btc-research"


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class RailwayHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in {"/", "/api/health", "/health"}:
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "service": SERVICE_NAME,
                    "mode": "research_only",
                    "execution_allowed": False,
                    "message": "HFT-BTC Railway service is running. Use the CLI pipeline for data/research jobs.",
                },
            )
            return

        _json_response(
            self,
            404,
            {
                "ok": False,
                "error": "not_found",
                "available_paths": ["/", "/api/health", "/health"],
            },
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), RailwayHandler)
    print(f"{SERVICE_NAME} listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

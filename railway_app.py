from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


SERVICE_NAME = "hft-btc-research"


def _health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "mode": "research_only",
        "execution_allowed": False,
        "message": "HFT-BTC Railway service is running. Use the CLI pipeline for data/research jobs.",
    }


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler: BaseHTTPRequestHandler, status: int, html: str) -> None:
    body = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _dashboard_html() -> str:
    payload = _health_payload()
    health_json = json.dumps(payload, indent=2)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HFT-BTC Research Dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07111f;
      --panel: rgba(15, 23, 42, 0.86);
      --panel-2: rgba(30, 41, 59, 0.72);
      --text: #e5eefb;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-2: #22c55e;
      --warn: #f59e0b;
      --border: rgba(148, 163, 184, 0.22);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.24), transparent 30rem),
        radial-gradient(circle at 80% 20%, rgba(34, 197, 94, 0.14), transparent 26rem),
        linear-gradient(135deg, #020617 0%, var(--bg) 58%, #0f172a 100%);
    }}
    .page {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 42px 0;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.35fr 0.65fr;
      gap: 22px;
      align-items: stretch;
    }}
    .card {{
      border: 1px solid var(--border);
      background: var(--panel);
      border-radius: 28px;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.36);
      backdrop-filter: blur(14px);
    }}
    .hero-main {{ padding: 34px; }}
    .eyebrow {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 7px 11px;
      border-radius: 999px;
      background: rgba(34, 197, 94, 0.14);
      color: #bbf7d0;
      border: 1px solid rgba(34, 197, 94, 0.24);
      font-weight: 700;
      font-size: 13px;
      letter-spacing: 0.02em;
    }}
    .dot {{
      width: 9px;
      height: 9px;
      background: var(--accent-2);
      border-radius: 999px;
      box-shadow: 0 0 18px rgba(34, 197, 94, 0.9);
    }}
    h1 {{
      margin: 22px 0 12px;
      font-size: clamp(36px, 5vw, 64px);
      line-height: 0.95;
      letter-spacing: -0.06em;
    }}
    .subtitle {{
      max-width: 780px;
      color: var(--muted);
      font-size: 18px;
      line-height: 1.65;
      margin: 0 0 26px;
    }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 12px; }}
    .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 0 16px;
      border-radius: 14px;
      color: var(--text);
      text-decoration: none;
      font-weight: 800;
      border: 1px solid var(--border);
      background: rgba(148, 163, 184, 0.10);
    }}
    .button.primary {{
      color: #03111f;
      background: linear-gradient(135deg, #67e8f9, #38bdf8);
      border: 0;
    }}
    .status-card {{ padding: 28px; }}
    .status-label {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.12em; }}
    .status-value {{ font-size: 38px; font-weight: 900; margin-top: 8px; color: #86efac; }}
    .pill-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 22px; }}
    .pill {{
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 8px 10px;
      background: rgba(15, 23, 42, 0.72);
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 18px;
      margin-top: 18px;
    }}
    .mini {{ padding: 24px; }}
    .mini h2 {{ margin: 0 0 8px; font-size: 18px; }}
    .mini p {{ margin: 0; color: var(--muted); line-height: 1.6; }}
    .code {{
      margin-top: 18px;
      padding: 22px;
      overflow: auto;
      border-radius: 22px;
      background: rgba(2, 6, 23, 0.82);
      border: 1px solid var(--border);
    }}
    pre {{ margin: 0; color: #c4b5fd; font-size: 13px; line-height: 1.55; }}
    .section-title {{ margin: 28px 0 12px; color: #cbd5e1; font-size: 14px; text-transform: uppercase; letter-spacing: 0.16em; }}
    .footer {{ color: var(--muted); font-size: 13px; margin-top: 18px; text-align: center; }}
    @media (max-width: 820px) {{
      .hero, .grid {{ grid-template-columns: 1fr; }}
      .hero-main, .status-card, .mini {{ padding: 22px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="card hero-main">
        <span class="eyebrow"><span class="dot"></span> Live on Railway</span>
        <h1>HFT-BTC Research Dashboard</h1>
        <p class="subtitle">
          A safe, research-only Bitcoin order-book platform for recording market data,
          reconstructing books, building features, training walk-forward models, and producing reports.
          Execution is disabled by design.
        </p>
        <div class="actions">
          <a class="button primary" href="/api/health">Open API health</a>
          <a class="button" href="/health">Open simple health</a>
        </div>
      </div>
      <aside class="card status-card">
        <div class="status-label">Service status</div>
        <div class="status-value">Healthy</div>
        <div class="pill-row">
          <span class="pill">service: {payload['service']}</span>
          <span class="pill">mode: {payload['mode']}</span>
          <span class="pill">execution: disabled</span>
        </div>
      </aside>
    </section>

    <div class="section-title">Pipeline</div>
    <section class="grid">
      <div class="card mini">
        <h2>1. Record</h2>
        <p>Capture public Bitfinex/Coinbase order-book data into local parquet partitions.</p>
      </div>
      <div class="card mini">
        <h2>2. Research</h2>
        <p>Replay books, generate features and labels, then train walk-forward XGBoost models.</p>
      </div>
      <div class="card mini">
        <h2>3. Report</h2>
        <p>Backtest out-of-sample predictions and write an auditable daily decision report.</p>
      </div>
    </section>

    <div class="section-title">Current health payload</div>
    <section class="card code">
      <pre>{health_json}</pre>
    </section>

    <div class="section-title">CLI examples</div>
    <section class="card code">
      <pre>python main.py record
python main.py replay --exchange bitfinex --symbol BTCUSD --start 2026-05-22 --end 2026-05-22
python main.py pipeline --exchange bitfinex --symbol BTCUSD --horizon 5 --start 2026-05-22 --end 2026-05-22</pre>
    </section>

    <p class="footer">Research code only. No private API keys. No order placement. No withdrawals.</p>
  </main>
</body>
</html>"""


class RailwayHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            _html_response(self, 200, _dashboard_html())
            return

        if self.path in {"/api/health", "/health"}:
            _json_response(self, 200, _health_payload())
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

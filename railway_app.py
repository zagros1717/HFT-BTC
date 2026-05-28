from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


SERVICE_NAME = "hft-btc-research"
DATA_ROOT = Path(os.getenv("DATA_ROOT", "data"))
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "mode": "research_only",
        "execution_allowed": False,
        "message": "HFT-BTC Railway service is running. Use the dashboard to run research-only data and training jobs.",
    }


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, indent=2, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler: BaseHTTPRequestHandler, status: int, html_body: str) -> None:
    body = html_body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _authorized(handler: BaseHTTPRequestHandler) -> bool:
    token = (os.getenv("DASHBOARD_TOKEN") or "").strip()
    if not token:
        return True
    supplied = (handler.headers.get("X-Dashboard-Token") or "").strip()
    return supplied == token


def _job_snapshot() -> list[dict[str, Any]]:
    with JOBS_LOCK:
        return sorted(
            [dict(job) for job in JOBS.values()],
            key=lambda j: j.get("created_at", ""),
            reverse=True,
        )


def _set_job(job_id: str, **patch: Any) -> None:
    with JOBS_LOCK:
        job = JOBS.setdefault(job_id, {"id": job_id})
        job.update(patch)


def _append_log(job_id: str, text: str) -> None:
    with JOBS_LOCK:
        job = JOBS.setdefault(job_id, {"id": job_id})
        current = job.get("log", "")
        job["log"] = (current + text)[-20000:]


def _start_job(kind: str, command: list[str], timeout_seconds: int | None = None) -> dict[str, Any]:
    job_id = f"{kind}_{uuid.uuid4().hex[:8]}"
    _set_job(
        job_id,
        kind=kind,
        command=" ".join(command),
        status="queued",
        created_at=_now(),
        started_at=None,
        finished_at=None,
        returncode=None,
        log="",
    )

    thread = threading.Thread(
        target=_run_command_job,
        args=(job_id, command, timeout_seconds),
        daemon=True,
    )
    thread.start()
    return JOBS[job_id]


def _run_command_job(job_id: str, command: list[str], timeout_seconds: int | None) -> None:
    _set_job(job_id, status="running", started_at=_now())
    _append_log(job_id, f"$ {' '.join(command)}\n\n")
    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
        _append_log(job_id, completed.stdout or "")
        _set_job(job_id, status="completed" if completed.returncode == 0 else "failed", returncode=completed.returncode)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        _append_log(job_id, output)
        _append_log(job_id, f"\nStopped after timeout ({timeout_seconds} seconds). The recorder should flush partial files on SIGTERM.\n")
        _set_job(job_id, status="completed", returncode=0, timed_out=True)
    except Exception as exc:
        _append_log(job_id, f"\nERROR: {exc}\n")
        _set_job(job_id, status="failed", returncode=1, error=str(exc))
    finally:
        _set_job(job_id, finished_at=_now())


def _safe_date(value: Any, default: str) -> str:
    text = str(value or default)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError("Date must use YYYY-MM-DD format")
    return text


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _data_summary() -> dict[str, Any]:
    def count(pattern: str) -> int:
        if not DATA_ROOT.exists():
            return 0
        return sum(1 for _ in DATA_ROOT.glob(pattern))

    latest_reports = []
    reports_dir = DATA_ROOT / "reports"
    if reports_dir.exists():
        for path in sorted(reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
            latest_reports.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                }
            )

    return {
        "data_root": str(DATA_ROOT),
        "exists": DATA_ROOT.exists(),
        "raw_parquet_files": count("raw/**/*.parquet"),
        "normalized_parquet_files": count("normalized/**/*.parquet"),
        "snapshot_parquet_files": count("snapshots/**/*.parquet"),
        "feature_parquet_files": count("features/**/*.parquet"),
        "label_parquet_files": count("labels/**/*.parquet"),
        "model_files": count("models/**/*"),
        "latest_reports": latest_reports,
    }


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HFT-BTC Research Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #07111f;
      --panel: rgba(15, 23, 42, 0.88);
      --panel-2: rgba(30, 41, 59, 0.72);
      --text: #e5eefb;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --good: #22c55e;
      --warn: #f59e0b;
      --bad: #fb7185;
      --border: rgba(148, 163, 184, 0.22);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.24), transparent 30rem),
        radial-gradient(circle at 80% 20%, rgba(34, 197, 94, 0.14), transparent 26rem),
        linear-gradient(135deg, #020617 0%, var(--bg) 58%, #0f172a 100%);
    }
    .page { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 38px 0; }
    .hero, .grid { display: grid; gap: 18px; }
    .hero { grid-template-columns: 1.3fr 0.7fr; align-items: stretch; }
    .grid { grid-template-columns: repeat(3, 1fr); }
    .card {
      border: 1px solid var(--border);
      background: var(--panel);
      border-radius: 26px;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.34);
      backdrop-filter: blur(14px);
      padding: 24px;
    }
    .hero-main { padding: 34px; }
    .eyebrow {
      display: inline-flex; gap: 8px; align-items: center; padding: 7px 11px;
      border-radius: 999px; background: rgba(34, 197, 94, 0.14); color: #bbf7d0;
      border: 1px solid rgba(34, 197, 94, 0.24); font-weight: 800; font-size: 13px;
    }
    .dot { width: 9px; height: 9px; background: var(--good); border-radius: 999px; box-shadow: 0 0 18px rgba(34, 197, 94, 0.9); }
    h1 { margin: 22px 0 12px; font-size: clamp(34px, 5vw, 62px); line-height: 0.95; letter-spacing: -0.06em; }
    h2 { margin: 0 0 12px; font-size: 20px; }
    h3 { margin: 0 0 8px; font-size: 15px; color: #cbd5e1; }
    p { color: var(--muted); line-height: 1.6; }
    .subtitle { max-width: 780px; font-size: 18px; margin: 0 0 24px; }
    .status-value { font-size: 38px; font-weight: 900; margin-top: 8px; color: #86efac; }
    .status-label { color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.12em; }
    .pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
    .pill {
      border: 1px solid var(--border); border-radius: 999px; padding: 8px 10px;
      background: rgba(15, 23, 42, 0.72); color: var(--muted); font-size: 13px; font-weight: 700;
    }
    label { display: block; color: #cbd5e1; font-size: 13px; font-weight: 800; margin: 12px 0 6px; }
    input, select {
      width: 100%; height: 42px; border-radius: 12px; border: 1px solid var(--border);
      background: rgba(2, 6, 23, 0.72); color: var(--text); padding: 0 12px; outline: none;
    }
    button, .button {
      display: inline-flex; align-items: center; justify-content: center; min-height: 42px;
      padding: 0 15px; border-radius: 13px; color: var(--text); text-decoration: none;
      font-weight: 900; border: 1px solid var(--border); background: rgba(148, 163, 184, 0.12); cursor: pointer;
    }
    button.primary, .button.primary { color: #03111f; background: linear-gradient(135deg, #67e8f9, #38bdf8); border: 0; }
    button.warn { color: #1c1203; background: linear-gradient(135deg, #fbbf24, #f59e0b); border: 0; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
    .section-title { margin: 28px 0 12px; color: #cbd5e1; font-size: 14px; text-transform: uppercase; letter-spacing: 0.16em; }
    .code, pre {
      background: rgba(2, 6, 23, 0.82); border: 1px solid var(--border); border-radius: 18px;
    }
    pre { margin: 0; padding: 18px; overflow: auto; color: #c4b5fd; font-size: 12px; line-height: 1.55; white-space: pre-wrap; }
    .job { border-top: 1px solid var(--border); padding-top: 14px; margin-top: 14px; }
    .job:first-child { border-top: 0; padding-top: 0; margin-top: 0; }
    .job-title { display: flex; gap: 8px; justify-content: space-between; align-items: center; }
    .badge { font-size: 12px; font-weight: 900; padding: 5px 8px; border-radius: 999px; background: rgba(148, 163, 184, 0.14); color: var(--muted); }
    .badge.running { color: #bae6fd; background: rgba(56, 189, 248, 0.15); }
    .badge.completed { color: #bbf7d0; background: rgba(34, 197, 94, 0.15); }
    .badge.failed { color: #fecdd3; background: rgba(251, 113, 133, 0.15); }
    .footer { color: var(--muted); font-size: 13px; margin-top: 18px; text-align: center; }
    @media (max-width: 900px) { .hero, .grid { grid-template-columns: 1fr; } .hero-main, .card { padding: 22px; } }
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="card hero-main">
        <span class="eyebrow"><span class="dot"></span> Live on Railway</span>
        <h1>HFT-BTC Research Dashboard</h1>
        <p class="subtitle">
          Capture live public BTC order-book data, then run the offline research pipeline:
          replay → features → labels → train → backtest/report. Execution is disabled by design.
        </p>
        <div class="actions">
          <a class="button primary" href="/api/health">API health</a>
          <button onclick="refresh()">Refresh status</button>
        </div>
      </div>
      <aside class="card">
        <div class="status-label">Service status</div>
        <div class="status-value">Healthy</div>
        <div class="pill-row">
          <span class="pill">research-only</span>
          <span class="pill">no trading</span>
          <span class="pill">BTC order book</span>
        </div>
        <p id="summary">Loading data summary…</p>
      </aside>
    </section>

    <div class="section-title">Run jobs</div>
    <section class="grid">
      <div class="card">
        <h2>1. Record BTC data</h2>
        <p>Starts the live recorder for a limited time. Default source is Bitfinex BTC/USD with Coinbase fallback.</p>
        <label>Duration minutes</label>
        <input id="recordDuration" type="number" min="1" max="360" value="30" />
        <label>Dashboard token, if set</label>
        <input id="tokenRecord" type="password" placeholder="optional DASHBOARD_TOKEN" />
        <div class="actions">
          <button class="primary" onclick="startRecord()">Start recording</button>
        </div>
      </div>

      <div class="card">
        <h2>2. Train / pipeline</h2>
        <p>Runs replay, features, labels, train, and report for a selected date range.</p>
        <label>Exchange</label>
        <select id="exchange"><option value="bitfinex">bitfinex</option><option value="coinbase">coinbase</option></select>
        <label>Symbol</label>
        <input id="symbol" value="BTCUSD" />
        <label>Start date</label>
        <input id="startDate" type="date" />
        <label>End date</label>
        <input id="endDate" type="date" />
        <label>Horizon seconds</label>
        <input id="horizon" type="number" value="5" />
        <label>Dashboard token, if set</label>
        <input id="tokenPipeline" type="password" placeholder="optional DASHBOARD_TOKEN" />
        <div class="actions">
          <button class="warn" onclick="startPipeline()">Run pipeline/train</button>
        </div>
      </div>

      <div class="card">
        <h2>3. Jobs & logs</h2>
        <p>Jobs run in the Railway container. For serious multi-day training, attach a Railway volume to preserve <code>./data</code>.</p>
        <div class="actions"><button onclick="refresh()">Refresh jobs</button></div>
        <div id="jobs"></div>
      </div>
    </section>

    <div class="section-title">Data summary</div>
    <section class="card code">
      <pre id="dataSummary">Loading…</pre>
    </section>

    <p class="footer">Research code only. No private API keys. No order placement. No withdrawals.</p>
  </main>

<script>
function todayIso() {
  return new Date().toISOString().slice(0, 10);
}
document.getElementById('startDate').value = todayIso();
document.getElementById('endDate').value = todayIso();

function headers(tokenInputId) {
  const token = document.getElementById(tokenInputId)?.value || '';
  const h = {'Content-Type': 'application/json'};
  if (token) h['X-Dashboard-Token'] = token;
  return h;
}

async function postJson(url, body, tokenInputId) {
  const res = await fetch(url, {method: 'POST', headers: headers(tokenInputId), body: JSON.stringify(body)});
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.error || JSON.stringify(payload));
  return payload;
}

async function startRecord() {
  try {
    const duration_minutes = Number(document.getElementById('recordDuration').value || 30);
    const payload = await postJson('/api/jobs/record', {duration_minutes}, 'tokenRecord');
    alert('Recording job started: ' + payload.job.id);
    refresh();
  } catch (err) {
    alert('Could not start recorder: ' + err.message);
  }
}

async function startPipeline() {
  try {
    const body = {
      exchange: document.getElementById('exchange').value,
      symbol: document.getElementById('symbol').value,
      start: document.getElementById('startDate').value,
      end: document.getElementById('endDate').value,
      horizon: Number(document.getElementById('horizon').value || 5)
    };
    const payload = await postJson('/api/jobs/pipeline', body, 'tokenPipeline');
    alert('Pipeline job started: ' + payload.job.id);
    refresh();
  } catch (err) {
    alert('Could not start pipeline: ' + err.message);
  }
}

function renderJobs(jobs) {
  const root = document.getElementById('jobs');
  if (!jobs.length) {
    root.innerHTML = '<p>No jobs yet.</p>';
    return;
  }
  root.innerHTML = jobs.map(job => `
    <div class="job">
      <div class="job-title">
        <strong>${job.id}</strong>
        <span class="badge ${job.status}">${job.status}</span>
      </div>
      <p>${job.command || ''}</p>
      <pre>${(job.log || '').slice(-3000)}</pre>
    </div>
  `).join('');
}

async function refresh() {
  const res = await fetch('/api/status');
  const payload = await res.json();
  document.getElementById('dataSummary').textContent = JSON.stringify(payload.data, null, 2);
  document.getElementById('summary').textContent =
    `raw=${payload.data.raw_parquet_files}, features=${payload.data.feature_parquet_files}, labels=${payload.data.label_parquet_files}, jobs=${payload.jobs.length}`;
  renderJobs(payload.jobs);
}
refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""


class RailwayHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            _html_response(self, 200, _dashboard_html())
            return

        if parsed.path in {"/api/health", "/health"}:
            _json_response(self, 200, _health_payload())
            return

        if parsed.path == "/api/status":
            _json_response(self, 200, {"ok": True, "health": _health_payload(), "data": _data_summary(), "jobs": _job_snapshot()})
            return

        _json_response(
            self,
            404,
            {
                "ok": False,
                "error": "not_found",
                "available_paths": ["/", "/api/health", "/health", "/api/status", "/api/jobs/record", "/api/jobs/pipeline"],
            },
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not _authorized(self):
            _json_response(self, 401, {"ok": False, "error": "unauthorized", "message": "Set X-Dashboard-Token to DASHBOARD_TOKEN."})
            return

        try:
            body = _read_json_body(self)

            if parsed.path == "/api/jobs/record":
                duration_minutes = _safe_int(body.get("duration_minutes"), default=30, minimum=1, maximum=360)
                timeout_seconds = duration_minutes * 60
                job = _start_job("record", [sys.executable, "main.py", "record"], timeout_seconds=timeout_seconds)
                _json_response(self, 202, {"ok": True, "job": job})
                return

            if parsed.path == "/api/jobs/pipeline":
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                exchange = str(body.get("exchange") or "bitfinex")
                if exchange not in {"bitfinex", "coinbase"}:
                    raise ValueError("exchange must be bitfinex or coinbase")

                default_symbol = "BTCUSD" if exchange == "bitfinex" else "BTC-USD"
                symbol = str(body.get("symbol") or default_symbol)
                start = _safe_date(body.get("start"), today)
                end = _safe_date(body.get("end"), start)
                horizon = _safe_int(body.get("horizon"), default=5, minimum=1, maximum=3600)

                command = [
                    sys.executable,
                    "main.py",
                    "pipeline",
                    "--exchange",
                    exchange,
                    "--symbol",
                    symbol,
                    "--start",
                    start,
                    "--end",
                    end,
                    "--horizon",
                    str(horizon),
                ]
                job = _start_job("pipeline", command, timeout_seconds=6 * 60 * 60)
                _json_response(self, 202, {"ok": True, "job": job})
                return

            _json_response(self, 404, {"ok": False, "error": "not_found"})
        except Exception as exc:
            _json_response(self, 400, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), RailwayHandler)
    print(f"{SERVICE_NAME} listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

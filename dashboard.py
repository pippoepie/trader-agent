"""Generates a self-contained dashboard.html summarizing decisions.jsonl
(and, if a valid SAXO_TOKEN is available, a live account/positions snapshot).

Usage: python dashboard.py
Then open dashboard.html in a browser (no server needed).
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

DECISIONS_PATH = "decisions.jsonl"
OUTPUT_PATH = "dashboard.html"

STATUS_GOOD = "#0ca30c"
STATUS_CRITICAL = "#d03b3b"
STATUS_MUTED = "#898781"

ACTION_COLOR = {"buy": STATUS_GOOD, "sell": STATUS_CRITICAL, "hold": STATUS_MUTED}


def load_decisions() -> list[dict]:
    if not os.path.exists(DECISIONS_PATH):
        return []
    entries = []
    with open(DECISIONS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    entries.sort(key=lambda e: e.get("timestamp", ""))
    return entries


def fetch_live_snapshot() -> dict | None:
    token = os.environ.get("SAXO_TOKEN", "").strip()
    if not token:
        return None
    base_url = os.environ.get("SAXO_BASE_URL", "https://gateway.saxobank.com/sim/openapi").rstrip("/")
    try:
        from saxo_client import SaxoClient, SaxoError

        client = SaxoClient(base_url, token)
        account = client.get_account()
        positions = client.get_positions()
        return {"account": account, "positions": positions}
    except Exception:
        return None


def compute_stats(decisions: list[dict]) -> dict:
    total = len(decisions)
    buy = sum(1 for d in decisions if d.get("decision", {}).get("action") == "buy")
    sell = sum(1 for d in decisions if d.get("decision", {}).get("action") == "sell")
    hold = sum(1 for d in decisions if d.get("decision", {}).get("action") == "hold")
    executed = sum(1 for d in decisions if d.get("executed"))
    dry_run = total - executed
    return {
        "total": total,
        "buy": buy,
        "sell": sell,
        "hold": hold,
        "executed": executed,
        "dry_run": dry_run,
    }


def stat_tile(label: str, value, dot_color: str | None = None) -> str:
    dot = f'<span class="dot" style="background:{dot_color}"></span>' if dot_color else ""
    return f"""
    <div class="tile">
      <div class="tile-label">{dot}{html.escape(label)}</div>
      <div class="tile-value">{html.escape(str(value))}</div>
    </div>"""


def render_timeline(decisions: list[dict]) -> str:
    if not decisions:
        return '<div class="empty">No decisions logged yet — run <code>python run.py</code> to generate the first one.</div>'

    times = []
    for d in decisions:
        ts = d.get("timestamp")
        try:
            times.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
        except (ValueError, AttributeError):
            times.append(None)

    valid = [t for t in times if t is not None]
    if not valid:
        return '<div class="empty">No valid timestamps to plot.</div>'

    t_min, t_max = min(valid), max(valid)
    span = (t_max - t_min).total_seconds() or 1

    width, height, pad = 900, 140, 40
    plot_w = width - 2 * pad

    dots = []
    for d, t in zip(decisions, times):
        if t is None:
            continue
        frac = (t - t_min).total_seconds() / span if span else 0.5
        x = pad + frac * plot_w
        action = d.get("decision", {}).get("action", "hold")
        color = ACTION_COLOR.get(action, STATUS_MUTED)
        symbol = html.escape(d.get("decision", {}).get("symbol", ""))
        qty = d.get("decision", {}).get("quantity", 0)
        executed = "executed" if d.get("executed") else "dry-run"
        tooltip = html.escape(f"{t.strftime('%Y-%m-%d %H:%M UTC')} · {action.upper()} {symbol} x{qty} ({executed})")
        dots.append(
            f'<circle cx="{x:.1f}" cy="{height / 2:.1f}" r="6" fill="{color}" '
            f'stroke="var(--surface-1)" stroke-width="2" class="dot-mark" '
            f'data-tooltip="{tooltip}"><title>{tooltip}</title></circle>'
        )

    axis_label_start = html.escape(t_min.strftime("%Y-%m-%d"))
    axis_label_end = html.escape(t_max.strftime("%Y-%m-%d"))

    return f"""
    <svg viewBox="0 0 {width} {height}" class="timeline-svg" role="img" aria-label="Decision timeline">
      <line x1="{pad}" y1="{height / 2}" x2="{width - pad}" y2="{height / 2}" class="baseline" />
      {"".join(dots)}
      <text x="{pad}" y="{height - 10}" class="axis-label">{axis_label_start}</text>
      <text x="{width - pad}" y="{height - 10}" class="axis-label" text-anchor="end">{axis_label_end}</text>
    </svg>"""


def render_table(decisions: list[dict]) -> str:
    if not decisions:
        return ""
    rows = []
    for d in reversed(decisions):
        dec = d.get("decision", {})
        action = dec.get("action", "")
        color = ACTION_COLOR.get(action, STATUS_MUTED)
        executed_badge = (
            '<span class="badge badge-executed">executed</span>'
            if d.get("executed")
            else '<span class="badge badge-dry">dry-run</span>'
        )
        qty_display = str(dec.get("quantity", ""))
        requested = d.get("model_requested_quantity")
        if requested is not None:
            qty_display += f" (model asked for {requested})"
        rows.append(f"""
        <tr>
          <td class="mono">{html.escape(d.get("timestamp", ""))}</td>
          <td><span class="dot" style="background:{color}"></span>{html.escape(action.upper())}</td>
          <td>{html.escape(dec.get("symbol", ""))}</td>
          <td class="mono">{html.escape(qty_display)}</td>
          <td>{executed_badge}</td>
          <td class="rationale">{html.escape(dec.get("rationale", ""))}</td>
        </tr>""")
    return f"""
    <table class="log-table">
      <thead>
        <tr><th>Time (UTC)</th><th>Action</th><th>Symbol</th><th>Qty</th><th>Status</th><th>Rationale</th></tr>
      </thead>
      <tbody>{"".join(rows)}</tbody>
    </table>"""


def render_positions(snapshot: dict | None) -> str:
    if not snapshot:
        return '<div class="empty">Live account data unavailable (no SAXO_TOKEN, expired token, or request failed) — showing decision log only.</div>'

    accounts_data = snapshot.get("account", {}).get("Data", [])
    account = accounts_data[0] if accounts_data else {}
    positions_data = snapshot.get("positions", {}).get("Data", [])

    tiles = (
        stat_tile("Account currency", account.get("Currency", "—"))
        + stat_tile("Account ID", account.get("AccountId", "—"))
        + stat_tile("Open positions", len(positions_data))
    )

    if not positions_data:
        pos_table = '<div class="empty">No open positions.</div>'
    else:
        rows = []
        for p in positions_data:
            base = p.get("PositionBase", {})
            rows.append(f"""
            <tr>
              <td>{html.escape(str(base.get("Uic", "")))}</td>
              <td>{html.escape(base.get("AssetType", ""))}</td>
              <td class="mono">{html.escape(str(base.get("Amount", "")))}</td>
              <td class="mono">{html.escape(str(base.get("OpenPrice", "")))}</td>
            </tr>""")
        pos_table = f"""
        <table class="log-table">
          <thead><tr><th>Uic</th><th>Asset type</th><th>Amount</th><th>Open price</th></tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""

    return f'<div class="tiles">{tiles}</div>{pos_table}'


def build_html(decisions: list[dict], stats: dict, snapshot: dict | None) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    kpi_tiles = "".join([
        stat_tile("Total decisions", stats["total"]),
        stat_tile("Buy", stats["buy"], STATUS_GOOD),
        stat_tile("Sell", stats["sell"], STATUS_CRITICAL),
        stat_tile("Hold", stats["hold"], STATUS_MUTED),
        stat_tile("Executed", stats["executed"]),
        stat_tile("Dry-run", stats["dry_run"]),
    ])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trader Agent Dashboard</title>
<style>
  .viz-root {{
    color-scheme: light;
    --surface-1:      #fcfcfb;
    --page-plane:     #f9f9f7;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --text-muted:     #898781;
    --gridline:       #e1e0d9;
    --baseline:       #c3c2b7;
    --border:         rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz-root {{
      color-scheme: dark;
      --surface-1:      #1a1a19;
      --page-plane:     #0d0d0d;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted:     #898781;
      --gridline:       #2c2c2a;
      --baseline:       #383835;
      --border:         rgba(255,255,255,0.10);
    }}
  }}
  :root[data-theme="dark"] .viz-root {{
    color-scheme: dark;
    --surface-1:      #1a1a19;
    --page-plane:     #0d0d0d;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted:     #898781;
    --gridline:       #2c2c2a;
    --baseline:       #383835;
    --border:         rgba(255,255,255,0.10);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background: var(--page-plane);
    color: var(--text-primary);
  }}
  .wrap {{ max-width: 960px; margin: 0 auto; padding: 32px 20px 64px; }}
  header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 24px; flex-wrap: wrap; gap: 8px; }}
  h1 {{ font-size: 22px; margin: 0; }}
  .meta {{ color: var(--text-secondary); font-size: 13px; }}
  .theme-toggle {{
    background: var(--surface-1); border: 1px solid var(--border); color: var(--text-primary);
    padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;
  }}
  .card {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px; margin-bottom: 20px;
  }}
  .card h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-secondary); margin: 0 0 16px; }}
  .tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; }}
  .tile {{ background: var(--page-plane); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }}
  .tile-label {{ font-size: 12px; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }}
  .tile-value {{ font-size: 22px; font-weight: 600; }}
  .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .empty {{ color: var(--text-muted); font-size: 13px; padding: 12px 0; }}
  .timeline-svg {{ width: 100%; height: auto; }}
  .baseline {{ stroke: var(--baseline); stroke-width: 1; }}
  .axis-label {{ fill: var(--text-muted); font-size: 11px; }}
  .dot-mark {{ cursor: pointer; }}
  .legend {{ display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary); margin-top: 8px; }}
  .legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
  table.log-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .log-table th {{ text-align: left; color: var(--text-secondary); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em; padding: 8px 10px; border-bottom: 1px solid var(--gridline); }}
  .log-table td {{ padding: 8px 10px; border-bottom: 1px solid var(--gridline); vertical-align: top; }}
  .log-table tr:hover td {{ background: var(--page-plane); }}
  .mono {{ font-variant-numeric: tabular-nums; }}
  .rationale {{ color: var(--text-secondary); max-width: 420px; }}
  .badge {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; }}
  .badge-executed {{ background: rgba(12,163,12,0.15); color: {STATUS_GOOD}; }}
  .badge-dry {{ background: rgba(137,135,129,0.15); color: var(--text-secondary); }}
</style>
</head>
<body>
<div class="viz-root">
  <div class="wrap">
    <header>
      <div>
        <h1>Trader Agent Dashboard</h1>
        <div class="meta">Generated {generated_at} · reads decisions.jsonl</div>
      </div>
      <button class="theme-toggle" onclick="toggleTheme()">Toggle theme</button>
    </header>

    <div class="card">
      <h2>Summary</h2>
      <div class="tiles">{kpi_tiles}</div>
    </div>

    <div class="card">
      <h2>Decision timeline</h2>
      {render_timeline(decisions)}
      <div class="legend">
        <span><span class="dot" style="background:{STATUS_GOOD}"></span>Buy</span>
        <span><span class="dot" style="background:{STATUS_CRITICAL}"></span>Sell</span>
        <span><span class="dot" style="background:{STATUS_MUTED}"></span>Hold</span>
      </div>
    </div>

    <div class="card">
      <h2>Live account snapshot</h2>
      {render_positions(snapshot)}
    </div>

    <div class="card">
      <h2>Decision log</h2>
      {render_table(decisions) or '<div class="empty">No decisions logged yet.</div>'}
    </div>
  </div>
</div>
<script>
function toggleTheme() {{
  const root = document.documentElement;
  const current = root.getAttribute('data-theme');
  root.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
}}
</script>
</body>
</html>"""


def main():
    decisions = load_decisions()
    stats = compute_stats(decisions)
    snapshot = fetch_live_snapshot()
    html_out = build_html(decisions, stats, snapshot)
    with open(OUTPUT_PATH, "w") as f:
        f.write(html_out)
    print(f"Wrote {OUTPUT_PATH} ({stats['total']} decisions logged).")


if __name__ == "__main__":
    main()

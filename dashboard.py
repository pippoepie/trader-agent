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
EQUITY_PATH = "equity_history.jsonl"
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
        from saxo_client import SaxoClient

        client = SaxoClient(base_url, token)
        account = client.get_account()
        positions = client.get_positions()
        try:
            balance = client.get_balance()
        except Exception:
            balance = None
        return {"account": account, "positions": positions, "balance": balance}
    except Exception:
        return None


def record_equity_snapshot(snapshot: dict | None) -> None:
    if not snapshot or not snapshot.get("balance"):
        return
    balance = snapshot["balance"]
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_value": balance.get("TotalValue"),
        "unrealized_pl": balance.get("UnrealizedMarginProfitLoss"),
        "cash_balance": balance.get("CashBalance"),
        "currency": balance.get("Currency", ""),
    }
    with open(EQUITY_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_equity_history() -> list[dict]:
    if not os.path.exists(EQUITY_PATH):
        return []
    entries = []
    with open(EQUITY_PATH) as f:
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


def format_signed(value, currency: str = "") -> str:
    sign = "+" if value >= 0 else ""
    text = f"{sign}{value:,.2f}"
    return f"{text} {currency}".strip()


def render_pl_chart(history: list[dict]) -> str:
    if not history:
        return (
            '<div class="empty">No equity snapshots yet — each time you run '
            '<code>dashboard.py</code> with a valid SAXO_TOKEN, a snapshot is recorded here. '
            "Run it a few more times (e.g. after each <code>run.py</code> cycle) to build a trend.</div>"
        )

    paired = []
    for h in history:
        pl = h.get("unrealized_pl")
        ts = h.get("timestamp")
        if pl is None or not ts:
            continue
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        paired.append((t, pl))

    if len(paired) < 2:
        if paired:
            t, pl = paired[0]
            currency = history[-1].get("currency", "")
            return (
                f'<div class="empty">Only one snapshot so far: {format_signed(pl, currency)}. '
                "Run <code>python dashboard.py</code> again later (after more trading cycles) "
                "to start building a P&amp;L trend line.</div>"
            )
        return '<div class="empty">No valid equity snapshots to plot yet.</div>'

    t_min = min(t for t, _ in paired)
    t_max = max(t for t, _ in paired)
    span = (t_max - t_min).total_seconds() or 1

    pl_values = [pl for _, pl in paired]
    pl_min, pl_max = min(0, *pl_values), max(0, *pl_values)
    pl_range = (pl_max - pl_min) or 1
    pl_min -= pl_range * 0.15
    pl_max += pl_range * 0.15
    pl_range = pl_max - pl_min

    width, height, pad = 900, 180, 44
    plot_w = width - 2 * pad
    plot_h = height - 2 * pad

    def x_for(t):
        frac = (t - t_min).total_seconds() / span
        return pad + frac * plot_w

    def y_for(pl):
        frac = (pl - pl_min) / pl_range
        return pad + plot_h - frac * plot_h

    zero_y = y_for(0)
    latest_pl = paired[-1][1]
    latest_currency = history[-1].get("currency", "")
    line_color = STATUS_GOOD if latest_pl >= 0 else STATUS_CRITICAL

    points = [(x_for(t), y_for(pl)) for t, pl in paired]
    polyline_points = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    dots = []
    for (t, pl), (x, y) in zip(paired, points):
        tooltip = html.escape(f"{t.strftime('%Y-%m-%d %H:%M UTC')} · {format_signed(pl, latest_currency)}")
        dots.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{line_color}" '
            f'stroke="var(--surface-1)" stroke-width="2" class="dot-mark" '
            f'data-tooltip="{tooltip}"><title>{tooltip}</title></circle>'
        )

    end_x, end_y = points[-1]
    end_label = html.escape(format_signed(latest_pl, latest_currency))
    axis_label_start = html.escape(t_min.strftime("%Y-%m-%d %H:%M"))
    axis_label_end = html.escape(t_max.strftime("%Y-%m-%d %H:%M"))

    return f"""
    <svg viewBox="0 0 {width} {height}" class="timeline-svg" role="img" aria-label="Unrealized profit and loss over time">
      <line x1="{pad}" y1="{zero_y:.1f}" x2="{width - pad}" y2="{zero_y:.1f}" class="baseline" />
      <polyline points="{polyline_points}" fill="none" stroke="{line_color}" stroke-width="2" \
stroke-linejoin="round" stroke-linecap="round" />
      {"".join(dots)}
      <text x="{end_x:.1f}" y="{end_y - 12:.1f}" class="axis-label pl-end-label" text-anchor="end">{end_label}</text>
      <text x="{pad}" y="{height - 10}" class="axis-label">{axis_label_start}</text>
      <text x="{width - pad}" y="{height - 10}" class="axis-label" text-anchor="end">{axis_label_end}</text>
    </svg>"""


def render_profit_tracker(snapshot: dict | None, history: list[dict]) -> str:
    if not snapshot or not snapshot.get("balance"):
        return (
            '<div class="empty">Live account data unavailable (no SAXO_TOKEN, expired token, '
            "or the balances request failed) — profit tracking needs a working Saxo connection.</div>"
        )

    balance = snapshot["balance"]
    currency = balance.get("Currency", "")
    unrealized = balance.get("UnrealizedMarginProfitLoss")
    total_value = balance.get("TotalValue")
    cash_balance = balance.get("CashBalance")

    pl_color = None
    if unrealized is not None:
        pl_color = STATUS_GOOD if unrealized >= 0 else STATUS_CRITICAL

    tiles = "".join([
        stat_tile(
            "Unrealized P&L",
            format_signed(unrealized, currency) if unrealized is not None else "—",
            pl_color,
        ),
        stat_tile("Total account value", f"{total_value:,.2f} {currency}" if total_value is not None else "—"),
        stat_tile("Cash balance", f"{cash_balance:,.2f} {currency}" if cash_balance is not None else "—"),
    ])

    return f'<div class="tiles">{tiles}</div>{render_pl_chart(history)}'


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
            view = p.get("PositionView", {})
            pl = view.get("ProfitLossOnTradeInBaseCurrency")
            pl_cell = (
                f'<span style="color:{STATUS_GOOD if pl >= 0 else STATUS_CRITICAL}">{format_signed(pl)}</span>'
                if pl is not None
                else "—"
            )
            rows.append(f"""
            <tr>
              <td>{html.escape(str(base.get("Uic", "")))}</td>
              <td>{html.escape(base.get("AssetType", ""))}</td>
              <td class="mono">{html.escape(str(base.get("Amount", "")))}</td>
              <td class="mono">{html.escape(str(base.get("OpenPrice", "")))}</td>
              <td class="mono">{html.escape(str(view.get("CurrentPrice", "—")))}</td>
              <td class="mono">{pl_cell}</td>
            </tr>""")
        pos_table = f"""
        <table class="log-table">
          <thead><tr><th>Uic</th><th>Asset type</th><th>Amount</th><th>Open price</th><th>Current price</th><th>P&amp;L</th></tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""

    return f'<div class="tiles">{tiles}</div>{pos_table}'


def build_html(decisions: list[dict], stats: dict, snapshot: dict | None, equity_history: list[dict]) -> str:
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
<meta http-equiv="refresh" content="900">
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
  .pl-end-label {{ fill: var(--text-primary); font-size: 13px; font-weight: 600; }}
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
        <div class="meta">Generated {generated_at} · auto-refreshes every 15 min, in sync with the trading cycle</div>
      </div>
      <button class="theme-toggle" onclick="toggleTheme()">Toggle theme</button>
    </header>

    <div class="card">
      <h2>Summary</h2>
      <div class="tiles">{kpi_tiles}</div>
    </div>

    <div class="card">
      <h2>Profit tracker</h2>
      {render_profit_tracker(snapshot, equity_history)}
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
    record_equity_snapshot(snapshot)
    equity_history = load_equity_history()
    html_out = build_html(decisions, stats, snapshot, equity_history)
    with open(OUTPUT_PATH, "w") as f:
        f.write(html_out)
    print(f"Wrote {OUTPUT_PATH} ({stats['total']} decisions logged, {len(equity_history)} equity snapshots).")


if __name__ == "__main__":
    main()

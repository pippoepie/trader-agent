# Saxo SIM Trading Agent

An LLM-assisted trading agent for Saxo Bank's **simulation (paper trading)** environment.
Each run: fetches your SIM account/positions/quotes, asks Claude for a single buy/sell/hold
decision, applies basic risk limits, and (only if you opt in) places the order.

**This is not investment advice, and it only talks to Saxo's SIM environment — no real
money is ever involved unless you rewire it to point at the live API, which this project
deliberately does not do.**

## 1. Set up Saxo SIM access

1. Create a developer account at https://www.developer.saxo/.
2. Create a **Simulation Application** (App management → Create new app). Note the AppKey/AppSecret
   (not directly used by this project, but required to generate a token).
3. Generate a **24-Hour Access Token** from the developer portal (Token page) for your simulation app.
   This is the simplest way to authenticate without implementing full OAuth2 — but it expires every
   24 hours, so you'll need to re-generate and re-paste it into `.env` each day you use the agent.
4. Confirm the SIM base URL is still `https://gateway.saxobank.com/sim/openapi` (check developer.saxo's
   reference docs — Saxo occasionally changes environment details).

## 2. Set up Anthropic access

Get an API key from https://console.anthropic.com/settings/keys.

## 3. Configure

```bash
cd saxo_trading_agent
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: paste SAXO_TOKEN and ANTHROPIC_API_KEY, adjust WATCHLIST
```

## 4. Run

```bash
python run.py            # dry run — logs the decision, does not place an order
python run.py --execute   # actually places the order on Saxo SIM (or set EXECUTE=true in .env)
```

Every run appends a line to `decisions.jsonl` with the timestamp, the model's decision, and
(if executed) the order result — use this as your audit trail.

## 5. Dashboard

```bash
python dashboard.py
open dashboard.html   # macOS; or just double-click the file
```

Generates a self-contained `dashboard.html` (no server, works offline) summarizing:
- decision counts (buy/sell/hold, executed/dry-run)
- a timeline of every decision
- a live account/positions snapshot (if `SAXO_TOKEN` is still valid)
- the full decision log with rationale

Regenerate it any time after new runs to see the latest state. `dashboard.html` itself is
gitignored (it can contain live account data) — only the generator script is committed.

## First-run checklist

Saxo's API surface can differ slightly from what's documented here depending on account type
and API version changes. The first time you run this, check in order:

1. `get_account()` succeeds (auth is working).
2. `search_instrument()` returns a real Uic for each watchlist symbol.
3. A full dry run (`python run.py`) produces a sensible decision and logs it.
4. Only then try `--execute` and confirm a SIM order actually appears in your Saxo SIM account.

## Limitations / next steps

- **24-hour token only.** No refresh-token OAuth2 flow is implemented, so this isn't suited to
  running unattended for days — plan to re-paste a fresh token daily, or implement the full
  OAuth2 Authorization Code flow (documented at developer.saxo) if you want that.
- **No live trading path.** Switching to Saxo's live environment would require your own review
  of the risk controls in `risk.py` — treat that as a deliberate, separate decision, not a config flip.
- **Single-cycle, not a daemon.** Run manually or via cron; there's no built-in polling loop.
- **Risk controls are minimal.** `risk.py` only clamps quantity and enforces the watchlist —
  no daily-loss limits, no max-open-positions check. Extend before trusting it with anything
  beyond small SIM trades.

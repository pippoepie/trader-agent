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
cd trader-agent
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: paste SAXO_TOKEN and ANTHROPIC_API_KEY, adjust WATCHLIST
```

**Important — SIM only gives real market data for Forex.** Saxo's own docs confirm equities/ETFs
always return `NoAccess` for bid/ask in the simulation environment (there's no setting that fixes
this short of linking to a live account). The default `WATCHLIST` is therefore Forex pairs
(`EURUSD,USDJPY,GBPUSD`) with `ASSET_TYPE=FxSpot` — that's what actually gets tradable quotes today.
If you switch `ASSET_TYPE` to `Stock` you'll be back to `NoAccess` quotes and the agent will always hold.

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
- **a profit tracker** — unrealized P&L, total account value, cash balance, and a P&L trend
  line (built from a snapshot recorded to `equity_history.jsonl` every time you run
  `dashboard.py` — the trend line needs at least 2 runs to appear)
- a live account/positions snapshot (if `SAXO_TOKEN` is still valid), including per-position P&L
- the full decision log with rationale

Regenerate it any time after new runs to see the latest state — running it more often (e.g. after
each `run.py` cycle) builds a denser P&L trend. `dashboard.html` and `equity_history.jsonl` are
both gitignored (they can contain live account data) — only the generator script is committed.

## 6. Automation (runs unattended, auto-executes trades)

`automate.sh` runs one full cycle (`run.py --execute` then `dashboard.py`) and appends output to
`automation.log`. A `com.traderagent.autorun.plist` is provided for macOS's `launchd` scheduler,
set to run every 15 minutes. **This means it will autonomously place real SIM orders with no human
review, on a schedule, indefinitely** — that's a meaningfully bigger step than running `run.py`
yourself, so installing it is a deliberate action you take, not something done for you:

```bash
cp com.traderagent.autorun.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.traderagent.autorun.plist
```

Check `automation.log` (and `launchd_stdout.log` / `launchd_stderr.log`) periodically — nothing
alerts you if a cycle fails.

**The 24-hour token limit still applies.** `SAXO_TOKEN` expires roughly once a day; once it does,
every scheduled cycle will fail (visible in `automation.log`) until you paste in a fresh token.
There's no notification — check the log yourself, or accept it'll silently stop trading until you do.

To stop it:
```bash
launchctl unload ~/Library/LaunchAgents/com.traderagent.autorun.plist
```

### Dashboard refresh cadence

`dashboard.html` auto-refreshes itself in the browser (`<meta http-equiv="refresh" content="900">`)
every 15 minutes — matching `automate.sh`'s own cycle, since `dashboard.py` runs right after
`run.py --execute` in the same job. There's no separate faster job: the profit tracker updates
exactly when the trading cycle does, nothing in between. If you want to see the very latest state
sooner than that, just run `python3 dashboard.py` yourself, or open `dashboard.html` after checking
`automation.log` shows a fresh cycle.

Note: `equity_history.jsonl` grows by one line every time `dashboard.py` runs, so with this job
installed that's roughly one snapshot per minute instead of one per 15 minutes — harmless for a
local file, but the P&L trend line will get much denser.

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
- **`run.py`/`dashboard.py` themselves are single-cycle** — `automate.sh` + the launchd job (see
  §6) is what adds scheduling on top; there's no built-in polling loop inside the Python code itself.
- **Risk controls are still basic.** `risk.py` clamps per-order quantity, enforces the
  watchlist, and caps total exposure per symbol (`MAX_SYMBOL_EXPOSURE`, buy-only — selling to
  close is never blocked) — but there's still no daily-loss limit and no cap on the number of
  *distinct* symbols/positions open at once. Extend before trusting it with anything beyond
  small SIM trades.
- **FX position sizing.** `MAX_ORDER_QUANTITY` is in currency units, not "shares" — Saxo's typical
  FxSpot minimum is around 1,000 units. Don't reuse a stock-sized quantity cap for FX.

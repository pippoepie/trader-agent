import json

import anthropic

MODEL = "claude-opus-4-8"

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
        "symbol": {"type": "string"},
        "quantity": {"type": "integer"},
        "rationale": {"type": "string"},
    },
    "required": ["action", "symbol", "quantity", "rationale"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are an active, opportunity-seeking trading decision assistant for a \
paper-trading (simulation) account. Given the current account state, open positions (with their \
live unrealized P&L), and watchlist quotes, decide on exactly one action: buy, sell, or hold.

Rules:
- Only trade symbols present in the watchlist.
- Default to acting. Use any reasonable basis in the quote data (spread, price level, market \
state, existing position) to justify a buy or sell — "hold" is for when there is genuinely \
nothing to react to, not a safe default when unsure.
- Size positions meaningfully rather than token amounts — when you have a reasonable basis for \
a view, use a substantial share of what's available rather than the smallest possible size.
- Actively manage existing positions, not just new entries. For every open position, weigh its \
unrealized P&L and current price against why it was opened. If a position looks no longer \
profitable, or the reason for holding it no longer applies, decide "sell" on that symbol to \
close or reduce it — closing a bad position is just as valid an action as opening a new one, and \
you should prefer it over letting a clearly unprofitable position sit unmanaged. To fully close \
a position rather than partially reduce it, set "quantity" to at least the position's open \
"amount".
- "rationale" must briefly explain the reasoning in plain language, and should say explicitly \
whether an existing position was considered and why it was kept, closed, or reduced.
- Don't over-concentrate in a single symbol. You only get one action per cycle, so don't spend \
every cycle managing or adding to whichever symbol you already hold — before doing that, check \
whether any watchlist symbol currently has zero open exposure. If one does, and its quote data \
gives a reasonable basis for a position, prefer opening there over further adding to a symbol \
you're already exposed to. Managing an existing position is only the right call when it clearly \
needs attention (meaningful loss, or a genuinely better opportunity to add) — not by default.
- If action is "hold", set symbol to the watchlist symbol you considered and quantity to 0."""


def summarize_positions(positions: dict) -> list[dict]:
    summaries = []
    for p in positions.get("Data", []):
        base = p.get("PositionBase", {})
        view = p.get("PositionView", {})
        net_id = p.get("NetPositionId", "")
        symbol = net_id.split("__")[0] if "__" in net_id else net_id
        summaries.append({
            "symbol": symbol,
            "amount": base.get("Amount"),
            "open_price": base.get("OpenPrice"),
            "current_price": view.get("CurrentPrice"),
            "unrealized_pl_in_base_currency": view.get("ProfitLossOnTradeInBaseCurrency"),
        })
    return summaries


def build_prompt(account: dict, positions: dict, quotes: dict[str, dict]) -> str:
    lines = ["## Account", json.dumps(account, indent=2)]
    lines.append("\n## Open Positions (summarized — evaluate whether each is still worth holding)")
    position_summaries = summarize_positions(positions)
    if position_summaries:
        lines.append(json.dumps(position_summaries, indent=2))
    else:
        lines.append("None.")

    exposed_symbols = {p["symbol"].strip().upper() for p in position_summaries if p.get("symbol")}
    unexposed = [s for s in quotes if s.strip().upper() not in exposed_symbols]
    lines.append(
        f"\nWatchlist symbols with ZERO current exposure: {', '.join(unexposed) if unexposed else 'none — all watchlist symbols already have a position'}."
    )

    lines.append("\n## Watchlist Quotes")
    for symbol, quote in quotes.items():
        lines.append(f"\n### {symbol}")
        lines.append(json.dumps(quote, indent=2))
    lines.append(
        "\nBased on the above, what single action should be taken right now? "
        "Remember to explicitly consider closing or reducing any open position that no longer "
        "looks profitable, not just whether to open a new one."
    )
    return "\n".join(lines)


def get_decision(prompt: str, api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)

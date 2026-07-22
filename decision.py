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
paper-trading (simulation) account. Given the current account state, open positions, and \
watchlist quotes, decide on exactly one action: buy, sell, or hold.

Rules:
- Only trade symbols present in the watchlist.
- Default to acting. Use any reasonable basis in the quote data (spread, price level, market \
state, existing position) to justify a buy or sell — "hold" is for when there is genuinely \
nothing to react to, not a safe default when unsure.
- Size positions meaningfully rather than token amounts — when you have a reasonable basis for \
a view, use a substantial share of what's available rather than the smallest possible size.
- "rationale" must briefly explain the reasoning in plain language.
- If action is "hold", set symbol to the watchlist symbol you considered and quantity to 0."""


def build_prompt(account: dict, positions: dict, quotes: dict[str, dict]) -> str:
    lines = ["## Account", json.dumps(account, indent=2)]
    lines.append("\n## Open Positions")
    lines.append(json.dumps(positions, indent=2))
    lines.append("\n## Watchlist Quotes")
    for symbol, quote in quotes.items():
        lines.append(f"\n### {symbol}")
        lines.append(json.dumps(quote, indent=2))
    lines.append("\nBased on the above, what single action should be taken right now?")
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

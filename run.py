import argparse
import json
import sys
from datetime import datetime, timezone

from config import Config, ConfigError
from decision import build_prompt, get_decision, summarize_positions
from risk import clamp_quantity, clamp_to_exposure_cap, is_symbol_allowed, total_exposure
from saxo_client import SaxoClient, SaxoError

LOG_PATH = "decisions.jsonl"


def log_entry(entry: dict) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Saxo SIM LLM trading agent — one decision cycle.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually place the order on Saxo SIM. Without this flag, the agent only logs its decision.",
    )
    args = parser.parse_args()

    try:
        config = Config()
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1

    execute = config.execute or args.execute

    saxo = SaxoClient(config.saxo_base_url, config.saxo_token)

    try:
        account = saxo.get_account()
        positions = saxo.get_positions()

        quotes = {}
        instruments = {}
        for symbol in config.watchlist:
            instrument = saxo.search_instrument(symbol, asset_type=config.asset_type)
            if instrument is None:
                print(f"Warning: no instrument found for {symbol}, skipping.", file=sys.stderr)
                continue
            instruments[symbol] = instrument
            quotes[symbol] = saxo.get_quote(instrument["Identifier"], asset_type=config.asset_type)
    except SaxoError as e:
        print(f"Saxo API error while fetching data: {e}", file=sys.stderr)
        return 1

    if not quotes:
        print("No quotes available for any watchlist symbol — aborting.", file=sys.stderr)
        return 1

    prompt = build_prompt(account, positions, quotes)
    decision = get_decision(prompt, config.anthropic_api_key)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "executed": False,
    }

    if decision["action"] == "hold":
        print(f"HOLD — {decision['rationale']}")
        log_entry(entry)
        return 0

    symbol = decision["symbol"].strip().upper()
    if not is_symbol_allowed(symbol, config.watchlist):
        print(f"Model suggested {symbol}, which is not in the watchlist — refusing to trade.", file=sys.stderr)
        entry["executed"] = False
        entry["reject_reason"] = "symbol_not_allowed"
        log_entry(entry)
        return 1

    original_requested_quantity = decision["quantity"]
    quantity = clamp_quantity(original_requested_quantity, config.max_order_quantity)

    if decision["action"] == "buy":
        existing_exposure = total_exposure(summarize_positions(positions), symbol)
        quantity = clamp_to_exposure_cap(existing_exposure, quantity, config.max_symbol_exposure)

    if quantity != original_requested_quantity:
        entry["model_requested_quantity"] = original_requested_quantity
    decision["quantity"] = quantity

    if quantity <= 0:
        print(f"Decision quantity clamped to 0 (order/exposure limits) — nothing to do. Rationale: {decision['rationale']}")
        log_entry(entry)
        return 0

    instrument = instruments.get(symbol)
    if instrument is None:
        print(f"No resolved instrument for {symbol} — cannot place order.", file=sys.stderr)
        entry["reject_reason"] = "instrument_not_resolved"
        log_entry(entry)
        return 1

    buy_sell = "Buy" if decision["action"] == "buy" else "Sell"
    print(f"{decision['action'].upper()} {quantity} {symbol} — {decision['rationale']}")

    if not execute:
        print("Dry run (EXECUTE=false, no --execute flag): order NOT placed.")
        log_entry(entry)
        return 0

    try:
        account_key = account["Data"][0]["AccountKey"]
        order_result = saxo.place_order(
            account_key, instrument["Identifier"], buy_sell, quantity, asset_type=config.asset_type
        )
        print("Order placed:", json.dumps(order_result, indent=2))
        entry["executed"] = True
        entry["order_result"] = order_result
    except SaxoError as e:
        print(f"Order failed: {e}", file=sys.stderr)
        entry["executed"] = False
        entry["order_error"] = str(e)
        log_entry(entry)
        return 1

    log_entry(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())

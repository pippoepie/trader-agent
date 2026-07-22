from __future__ import annotations


def clamp_quantity(quantity: int, max_quantity: int) -> int:
    return max(0, min(quantity, max_quantity))


def is_symbol_allowed(symbol: str, watchlist: list[str]) -> bool:
    return symbol.strip().upper() in watchlist


def total_exposure(position_summaries: list[dict], symbol: str) -> float:
    symbol = symbol.strip().upper()
    return sum(
        abs(p.get("amount") or 0)
        for p in position_summaries
        if (p.get("symbol") or "").strip().upper() == symbol
    )


def clamp_to_exposure_cap(existing_exposure: float, requested_quantity: int, max_symbol_exposure: float) -> int:
    room = max_symbol_exposure - existing_exposure
    if room <= 0:
        return 0
    return max(0, min(requested_quantity, int(room)))

def clamp_quantity(quantity: int, max_quantity: int) -> int:
    return max(0, min(quantity, max_quantity))


def is_symbol_allowed(symbol: str, watchlist: list[str]) -> bool:
    return symbol.strip().upper() in watchlist

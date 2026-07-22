import os

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    pass


class Config:
    def __init__(self):
        self.saxo_token = os.environ.get("SAXO_TOKEN", "").strip()
        self.saxo_base_url = os.environ.get(
            "SAXO_BASE_URL", "https://gateway.saxobank.com/sim/openapi"
        ).rstrip("/")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.watchlist = [
            s.strip().upper()
            for s in os.environ.get("WATCHLIST", "").split(",")
            if s.strip()
        ]
        self.max_order_quantity = int(os.environ.get("MAX_ORDER_QUANTITY", "5"))
        self.execute = os.environ.get("EXECUTE", "false").strip().lower() == "true"

        if not self.saxo_token:
            raise ConfigError("SAXO_TOKEN is not set. Copy .env.example to .env and fill it in.")
        if not self.anthropic_api_key:
            raise ConfigError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
        if not self.watchlist:
            raise ConfigError("WATCHLIST is empty. Set at least one ticker in .env.")

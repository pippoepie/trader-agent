from __future__ import annotations

import requests


class SaxoError(RuntimeError):
    pass


class SaxoClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs):
        resp = self.session.request(method, f"{self.base_url}{path}", timeout=15, **kwargs)
        if not resp.ok:
            raise SaxoError(f"{method} {path} -> {resp.status_code}: {resp.text}")
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def get_account(self) -> dict:
        return self._request("GET", "/port/v1/accounts/me")

    def get_positions(self) -> dict:
        return self._request("GET", "/port/v1/positions/me")

    def search_instrument(self, keyword: str, asset_type: str = "Stock") -> dict | None:
        data = self._request(
            "GET",
            "/ref/v1/instruments",
            params={"Keywords": keyword, "AssetTypes": asset_type},
        )
        results = data.get("Data", [])
        return results[0] if results else None

    def get_quote(self, uic: int, asset_type: str = "Stock") -> dict:
        data = self._request(
            "GET",
            "/trade/v1/infoprices",
            params={"Uic": uic, "AssetType": asset_type},
        )
        return data

    def place_order(self, account_key: str, uic: int, buy_sell: str, amount: int, asset_type: str = "Stock") -> dict:
        body = {
            "AccountKey": account_key,
            "Uic": uic,
            "AssetType": asset_type,
            "BuySell": buy_sell,
            "Amount": amount,
            "OrderType": "Market",
            "OrderDuration": {"DurationType": "DayOrder"},
            "ManualOrder": True,
        }
        return self._request("POST", "/trade/v2/orders", json=body)

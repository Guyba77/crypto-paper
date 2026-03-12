from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass
class KrakenAuth:
    api_key: str
    api_secret_b64: str


class KrakenClient:
    """Minimal Kraken REST client for private endpoints.

    Notes:
    - This is intentionally small: only what we need for MVP execution.
    - Uses classic Kraken signing scheme (API-Sign).
    """

    def __init__(self, auth: KrakenAuth, base_url: str = "https://api.kraken.com"):
        self.auth = auth
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def from_env() -> "KrakenClient":
        key = os.environ.get("KRAKEN_API_KEY", "").strip()
        secret = os.environ.get("KRAKEN_API_SECRET", "").strip()
        if not key or not secret:
            raise RuntimeError("Missing Kraken credentials. Set KRAKEN_API_KEY and KRAKEN_API_SECRET (base64 secret).")
        return KrakenClient(KrakenAuth(api_key=key, api_secret_b64=secret))

    def _nonce(self) -> str:
        # Kraken expects an ever-increasing nonce per key.
        return str(int(time.time() * 1000))

    def _sign(self, url_path: str, data: Dict[str, Any]) -> str:
        postdata = urllib.parse.urlencode(data)
        encoded = (data["nonce"] + postdata).encode()
        message = url_path.encode() + hashlib.sha256(encoded).digest()
        secret = base64.b64decode(self.auth.api_secret_b64)
        sig = hmac.new(secret, message, hashlib.sha512).digest()
        return base64.b64encode(sig).decode()

    def _post_private(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        url_path = f"/0/private/{endpoint}"
        url = f"{self.base_url}{url_path}"

        data = dict(data)
        data.setdefault("nonce", self._nonce())

        headers = {
            "API-Key": self.auth.api_key,
            "API-Sign": self._sign(url_path, data),
            "User-Agent": "crypto-paper-mvp",
        }

        resp = requests.post(url, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        # Kraken returns {error:[], result:{...}}
        errs = payload.get("error") or []
        if errs:
            raise RuntimeError(f"Kraken error: {errs}")
        return payload.get("result") or {}

    # --- Public-ish helpers ---

    def add_order(
        self,
        pair: str,
        side: str,
        volume: float,
        ordertype: str = "market",
        validate: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        data: Dict[str, Any] = {
            "pair": pair,
            "type": side,
            "ordertype": ordertype,
            "volume": f"{volume:.10f}",
        }
        if validate:
            data["validate"] = "true"
        if extra:
            data.update(extra)
        return self._post_private("AddOrder", data)

    def cancel_all(self) -> Dict[str, Any]:
        return self._post_private("CancelAll", {})

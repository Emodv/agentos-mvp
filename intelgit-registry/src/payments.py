"""
Pluggable payment provider.
PAYMENT_PROVIDER env var: "stub" (default) | "localcredits" | "lightning"
"""
from __future__ import annotations

import os
import secrets
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from .db import get_conn, get_data_dir


class PaymentProvider(ABC):
    @abstractmethod
    def get_balance(self, user_id: str) -> int: ...  # in msat (1 USD ≈ 100_000_000_000 msat)

    @abstractmethod
    def pay(self, from_user: str, to_user: str, amount_msat: int, memo: str) -> str: ...

    @abstractmethod
    def deposit(self, user_id: str, amount_msat: int) -> str: ...


class StubProvider(PaymentProvider):
    """In-memory ledger — no real money, useful for tests and demos."""

    def __init__(self):
        self._balances: dict[str, int] = {}

    def get_balance(self, user_id: str) -> int:
        return self._balances.get(user_id, 100_000_000)  # 100 sat default

    def pay(self, from_user: str, to_user: str, amount_msat: int, memo: str) -> str:
        bal = self._balances.get(from_user, 100_000_000)
        if bal < amount_msat:
            raise ValueError("Insufficient balance (stub)")
        self._balances[from_user] = bal - amount_msat
        self._balances[to_user] = self._balances.get(to_user, 0) + amount_msat
        return f"stub_{secrets.token_hex(8)}"

    def deposit(self, user_id: str, amount_msat: int) -> str:
        self._balances[user_id] = self._balances.get(user_id, 0) + amount_msat
        return f"stub_deposit_{secrets.token_hex(8)}"


class LocalCreditsProvider(PaymentProvider):
    """SQLite-backed credit ledger — persisted, no real money."""

    def _init(self):
        conn = get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                from_agent TEXT,
                to_agent TEXT,
                ko_id TEXT,
                amount_msat INTEGER,
                status TEXT,
                tx_id TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def get_balance(self, user_id: str) -> int:
        conn = get_conn()
        row = conn.execute(
            "SELECT credits FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        conn.close()
        if not row:
            return 0
        return int(row["credits"] * 1000)  # credits → msat approximation

    def pay(self, from_user: str, to_user: str, amount_msat: int, memo: str) -> str:
        # Deduct and credit in one transaction
        amount_credits = amount_msat / 1000
        conn = get_conn()
        from_bal = (conn.execute(
            "SELECT credits FROM users WHERE id = ?", (from_user,)
        ).fetchone() or {"credits": 0})["credits"]
        if from_bal < amount_credits:
            conn.close()
            raise ValueError("Insufficient credits")
        conn.execute("UPDATE users SET credits = credits - ? WHERE id = ?",
                     (amount_credits, from_user))
        conn.execute("UPDATE users SET credits = credits + ? WHERE id = ?",
                     (amount_credits, to_user))
        tx_id = secrets.token_hex(12)
        conn.execute("""
            INSERT INTO payments (id, from_agent, to_agent, ko_id, amount_msat, status, tx_id, created_at)
            VALUES (?, ?, ?, ?, ?, 'settled', ?, ?)
        """, (secrets.token_hex(8), from_user, to_user, memo, amount_msat, tx_id,
              datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()
        return tx_id

    def deposit(self, user_id: str, amount_msat: int) -> str:
        amount_credits = amount_msat / 1000
        conn = get_conn()
        conn.execute("UPDATE users SET credits = credits + ? WHERE id = ?",
                     (amount_credits, user_id))
        conn.commit()
        conn.close()
        return f"deposit_{secrets.token_hex(8)}"


class LightningProvider(PaymentProvider):
    """
    Stub interface for LND REST API.
    Set LND_REST_URL and LND_MACAROON env vars to activate.
    Falls back to printing if LND not configured.
    """

    def __init__(self):
        self.url = os.environ.get("LND_REST_URL")
        self.macaroon = os.environ.get("LND_MACAROON")
        self._configured = bool(self.url and self.macaroon)

    def get_balance(self, user_id: str) -> int:
        if not self._configured:
            return 100_000_000
        import urllib.request
        req = urllib.request.Request(
            f"{self.url}/v1/balance/channels",
            headers={"Grpc-Metadata-macaroon": self.macaroon},
        )
        with urllib.request.urlopen(req) as r:
            import json
            data = json.loads(r.read())
            return int(data.get("local_balance", {}).get("msat", 0))

    def pay(self, from_user: str, to_user: str, amount_msat: int, memo: str) -> str:
        if not self._configured:
            print(f"[Lightning stub] Would pay {amount_msat} msat from {from_user} to {to_user}: {memo}")
            return f"lightning_stub_{secrets.token_hex(8)}"
        raise NotImplementedError("Full Lightning payment requires invoice; use LND keysend")

    def deposit(self, user_id: str, amount_msat: int) -> str:
        return f"ln_deposit_{secrets.token_hex(8)}"


def get_provider() -> PaymentProvider:
    name = os.environ.get("PAYMENT_PROVIDER", "localcredits").lower()
    if name == "stub":
        return StubProvider()
    if name == "lightning":
        return LightningProvider()
    return LocalCreditsProvider()


_provider: PaymentProvider | None = None


def provider() -> PaymentProvider:
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider

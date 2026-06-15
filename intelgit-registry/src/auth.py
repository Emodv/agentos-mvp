"""API key auth: generate sk_live_... keys, hash with SHA-256 for storage."""
import hashlib
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException

from .db import get_conn


def _generate_api_key() -> str:
    return "sk_live_" + secrets.token_hex(24)


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_user(display_name: str) -> tuple[str, str]:
    """Create a user and return (user_id, raw_api_key). Store hashed key."""
    raw = _generate_api_key()
    user_id = secrets.token_hex(16)
    conn = get_conn()
    conn.execute("""
        INSERT INTO users (id, display_name, api_key_hash, credits)
        VALUES (?, ?, ?, ?)
    """, (user_id, display_name, _hash_key(raw), 1000))
    conn.commit()
    conn.close()
    return user_id, raw


def get_user_by_key(raw_key: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE api_key_hash = ?", (_hash_key(raw_key),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def require_auth(x_api_key: Optional[str] = Header(None)) -> dict:
    """FastAPI dependency: require a valid X-API-Key header."""
    if not x_api_key:
        raise HTTPException(401, "X-API-Key header required")
    user = get_user_by_key(x_api_key)
    if not user:
        raise HTTPException(401, "Invalid API key")
    return user


def optional_auth(x_api_key: Optional[str] = Header(None)) -> Optional[dict]:
    if not x_api_key:
        return None
    return get_user_by_key(x_api_key)

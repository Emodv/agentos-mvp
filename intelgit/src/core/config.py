"""
User configuration stored in ~/.intelgit/config.json.
"""
import json
from pathlib import Path
from typing import Optional

_CONFIG_PATH = Path.home() / ".intelgit" / "config.json"
_DEFAULTS = {
    "registry_url": "https://hub.intelgit.ai",
    "signer_did": None,
    "private_key_pem": None,
}


def load() -> dict:
    if _CONFIG_PATH.exists():
        try:
            saved = json.loads(_CONFIG_PATH.read_text())
            return {**_DEFAULTS, **saved}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(cfg: dict):
    _CONFIG_PATH.parent.mkdir(exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def get(key: str):
    return load().get(key)


def set_value(key: str, value):
    cfg = load()
    cfg[key] = value
    save(cfg)


def get_or_create_identity() -> tuple[str, str]:
    """Return (did, pem), generating and persisting a new keypair if needed."""
    cfg = load()
    if cfg.get("signer_did") and cfg.get("private_key_pem"):
        return cfg["signer_did"], cfg["private_key_pem"]
    from .crypto import generate_did_key
    did, pem = generate_did_key()
    cfg["signer_did"] = did
    cfg["private_key_pem"] = pem
    save(cfg)
    return did, pem

"""Lightweight KO verification (no intelgit package dependency)."""
import base64
import hashlib
import json
from typing import Optional

import base58
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _canonical(obj: dict) -> bytes:
    obj_copy = {k: v for k, v in obj.items() if k != "id"}
    if isinstance(obj_copy.get("proof"), dict):
        proof = dict(obj_copy["proof"])
        proof.pop("signature", None)
        obj_copy["proof"] = proof
    return json.dumps(obj_copy, sort_keys=True, separators=(",", ":")).encode()


def verify_ko(ko: dict) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    Checks: ID integrity, signature validity.
    """
    # 1. ID check
    data = {k: v for k, v in ko.items() if k != "id"}
    canonical_all = json.dumps(data, sort_keys=True, separators=(",", ":"))
    expected_id = f"ko://sha256/{hashlib.sha256(canonical_all.encode()).hexdigest()}"
    if expected_id != ko.get("id"):
        return False, f"ID mismatch: expected {expected_id}"

    # 2. Signature check
    proof = ko.get("proof") or {}
    sig_b64 = proof.get("signature", "")
    did = proof.get("signer_did", "")
    if not sig_b64 or not did:
        return False, "Missing signature or signer_did"
    try:
        sig = base64.b64decode(sig_b64)
        pub_bytes = base58.b58decode(did.split(":")[-1][1:])
        pub: Ed25519PublicKey = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub.verify(sig, _canonical(ko))
        return True, "ok"
    except Exception as exc:
        return False, f"Signature invalid: {exc}"


def verify_output(ko: dict, output_bytes: bytes) -> bool:
    """Check that SHA3-256(output) matches the stored output_hash."""
    expected = hashlib.sha3_256(output_bytes).hexdigest()
    return expected == ko.get("output_hash", "")

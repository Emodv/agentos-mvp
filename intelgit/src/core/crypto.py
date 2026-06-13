import base64
import json

import base58
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization


def generate_did_key() -> tuple[str, str]:
    """Generate a new DID:key and return (did, private_key_pem)."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    # multibase base58-btc encoding (prefix 'z')
    did = f"did:key:z{base58.b58encode(pub_bytes).decode()}"
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return did, priv_pem


def _canonical(obj: dict) -> bytes:
    """Canonical JSON bytes: excludes top-level 'id' and proof.signature."""
    obj_copy = {k: v for k, v in obj.items() if k != "id"}
    if isinstance(obj_copy.get("proof"), dict):
        proof = dict(obj_copy["proof"])
        proof.pop("signature", None)
        obj_copy["proof"] = proof
    return json.dumps(obj_copy, sort_keys=True, separators=(",", ":")).encode()


def sign_object(obj: dict, private_key_pem: str) -> str:
    """Sign the canonical JSON of the object (excluding proof.signature)."""
    priv = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    sig = priv.sign(_canonical(obj))
    return base64.b64encode(sig).decode()


def verify_signature(obj: dict, signature_b64: str, did: str) -> bool:
    """Verify an ed25519 signature against a DID:key identifier."""
    try:
        sig = base64.b64decode(signature_b64)
        # Extract public key bytes: strip leading 'z' then base58-decode
        pub_bytes = base58.b58decode(did.split(":")[-1][1:])
        pub: Ed25519PublicKey = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub.verify(sig, _canonical(obj))
        return True
    except Exception:
        return False

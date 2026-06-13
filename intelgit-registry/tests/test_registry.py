"""Integration tests for the registry FastAPI server (v2 with auth)."""
import base64
import hashlib
import json
import os
import tempfile

# Point data dir at a temp directory before importing the app
_TMP = tempfile.mkdtemp()
os.environ["INTELGIT_DATA"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402
from src.main import app  # noqa: E402
from src.db import init_db  # noqa: E402

init_db()
client = TestClient(app)

# ── Shared auth fixture (module-level) ────────────────────────────────────────
_reg = client.post("/v1/register", json={"display_name": "test_user"})
assert _reg.status_code == 201, f"Registration failed: {_reg.text}"
_API_KEY = _reg.json()["api_key"]
_AUTH = {"X-API-Key": _API_KEY}


# ── KO builder ────────────────────────────────────────────────────────────────

def _make_ko(goal: str = "What is the capital of France?", output: str = "Paris") -> tuple[dict, bytes]:
    import base58
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    did = f"did:key:z{base58.b58encode(pub_bytes).decode()}"

    output_bytes = output.encode()
    output_hash = hashlib.sha3_256(output_bytes).hexdigest()

    ko: dict = {
        "goal": goal,
        "inputs": {},
        "output_hash": output_hash,
        "proof": {
            "model": "gpt-4-turbo",
            "execution_trace_hash": hashlib.sha256(output_bytes).hexdigest(),
            "signature": "",
            "signer_did": did,
        },
        "dependencies": [],
        "confidence": 0.99,
        "cost_usd": 0.001,
        "latency_ms": 600,
        "license": "reuse-with-attribution",
        "created_at": "2024-01-01T00:00:00+00:00",
    }

    # Sign
    payload = {k: v for k, v in ko.items()}
    proof_for_sign = dict(payload["proof"])
    proof_for_sign.pop("signature")
    payload["proof"] = proof_for_sign
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = base64.b64encode(priv.sign(canonical)).decode()
    ko["proof"]["signature"] = sig

    all_except_id = json.dumps(ko, sort_keys=True, separators=(",", ":"))
    ko["id"] = f"ko://sha256/{hashlib.sha256(all_except_id.encode()).hexdigest()}"

    return ko, output_bytes


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register():
    resp = client.post("/v1/register", json={"display_name": "alice"})
    assert resp.status_code == 201
    assert "api_key" in resp.json()
    assert resp.json()["api_key"].startswith("sk_live_")


def test_whoami():
    resp = client.get("/v1/whoami", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "test_user"


def test_whoami_unauthenticated():
    resp = client.get("/v1/whoami")
    assert resp.status_code == 401


def test_push_returns_201_and_verified():
    ko, out = _make_ko(goal="push test: capital of France")
    resp = client.post(
        "/v1/ko",
        data={"ko_json": json.dumps(ko)},
        files={"output": ("output.txt", out, "text/plain")},
        headers=_AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["verified"] is True
    assert body["id"] == ko["id"]


def test_push_requires_auth():
    ko, _ = _make_ko(goal="auth check push goal unique")
    resp = client.post("/v1/ko", data={"ko_json": json.dumps(ko)})
    assert resp.status_code == 401


def test_push_tampered_id_rejected():
    ko, _ = _make_ko(goal="unique tampered goal xyz 12345")
    ko["id"] = "ko://sha256/badidvalue"
    resp = client.post("/v1/ko", data={"ko_json": json.dumps(ko)}, headers=_AUTH)
    assert resp.status_code == 400


def test_push_output_hash_mismatch_rejected():
    ko, out = _make_ko(goal="hash mismatch test goal abc")
    resp = client.post(
        "/v1/ko",
        data={"ko_json": json.dumps(ko)},
        files={"output": ("o", b"wrong output", "text/plain")},
        headers=_AUTH,
    )
    assert resp.status_code == 400


def test_get_ko():
    ko, out = _make_ko(goal="get ko retrieval test goal unique 999")
    client.post("/v1/ko", data={"ko_json": json.dumps(ko)},
                files={"output": ("o", out, "text/plain")}, headers=_AUTH)
    resp = client.get(f"/v1/ko/{ko['id']}")
    assert resp.status_code == 200
    assert resp.json()["goal"] == ko["goal"]


def test_get_output():
    ko, out = _make_ko(goal="output retrieval goal unique test xyz")
    client.post("/v1/ko", data={"ko_json": json.dumps(ko)},
                files={"output": ("o", out, "text/plain")}, headers=_AUTH)
    resp = client.get(f"/v1/output/{ko['id']}")
    assert resp.status_code == 200
    assert resp.content == out


def test_search():
    ko, out = _make_ko(goal="capital of Japan is Tokyo search test unique")
    client.post("/v1/ko", data={"ko_json": json.dumps(ko)},
                files={"output": ("o", out, "text/plain")}, headers=_AUTH)
    resp = client.get("/v1/search?q=Japan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert any("Japan" in r["goal"] for r in data["results"])


def test_packages():
    ko, out = _make_ko(goal="package test KO goal unique 777")
    client.post("/v1/ko", data={"ko_json": json.dumps(ko)},
                files={"output": ("o", out, "text/plain")}, headers=_AUTH)
    # Create package
    resp = client.post("/v1/packages",
                       json={"name": "test/package", "ko_id": ko["id"], "description": "test"},
                       headers=_AUTH)
    assert resp.status_code == 201
    # Resolve package
    resp2 = client.get("/v1/packages/test/package")
    assert resp2.status_code == 200
    assert resp2.json()["package"]["latest_ko_id"] == ko["id"]


def test_balance():
    resp = client.get("/v1/balance", headers=_AUTH)
    assert resp.status_code == 200
    assert "balance_credits" in resp.json()


def test_leaderboard_returns_list():
    resp = client.get("/v1/leaderboard")
    assert resp.status_code == 200
    assert isinstance(resp.json()["results"], list)


def test_dashboard_home():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "IntelGit Hub" in resp.text


def test_ko_not_found():
    resp = client.get("/v1/ko/ko://sha256/doesnotexist")
    assert resp.status_code == 404

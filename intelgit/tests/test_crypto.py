from src.core.crypto import generate_did_key, sign_object, verify_signature


def test_generate_did_key_format():
    did, pem = generate_did_key()
    assert did.startswith("did:key:z")
    assert "BEGIN PRIVATE KEY" in pem


def test_sign_and_verify_roundtrip():
    did, pem = generate_did_key()
    obj = {"goal": "hello", "proof": {"model": "gpt-4", "execution_trace_hash": "xyz"}}
    sig = sign_object(obj, pem)
    assert verify_signature(obj, sig, did)


def test_verify_fails_on_tampered_data():
    did, pem = generate_did_key()
    obj = {"goal": "original", "proof": {"model": "gpt-4", "execution_trace_hash": "xyz"}}
    sig = sign_object(obj, pem)
    tampered = dict(obj, goal="tampered")
    assert not verify_signature(tampered, sig, did)


def test_verify_fails_on_wrong_did():
    did1, pem1 = generate_did_key()
    did2, _ = generate_did_key()
    obj = {"goal": "hello", "proof": {}}
    sig = sign_object(obj, pem1)
    assert not verify_signature(obj, sig, did2)


def test_signature_excluded_from_canonical():
    did, pem = generate_did_key()
    obj = {
        "goal": "test",
        "proof": {"model": "m", "execution_trace_hash": "h", "signature": "old_sig"},
    }
    sig = sign_object(obj, pem)
    # Adding/changing the signature field in proof should not affect verification
    obj["proof"]["signature"] = sig
    assert verify_signature(obj, sig, did)

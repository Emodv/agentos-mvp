"""
Demo: create, verify, and search knowledge objects without calling an LLM.
Run from the intelgit/ directory:
    python examples/demo.py
"""
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.core.crypto import generate_did_key, sign_object, verify_signature
from src.core.ko import KnowledgeObject, Proof
from src.core.store import KOLocalStore


def demo():
    print("=== IntelGit Demo ===\n")

    # 1. Generate an identity
    did, pem = generate_did_key()
    print(f"DID: {did}\n")

    # 2. Simulate LLM output
    goal = "What is the capital of France?"
    output_text = "The capital of France is Paris."
    output_hash = hashlib.sha3_256(output_text.encode()).hexdigest()

    proof = Proof(
        model="demo-model",
        execution_trace_hash=hashlib.sha256(output_text.encode()).hexdigest(),
        signature="",
        signer_did=did,
    )
    ko = KnowledgeObject(
        goal=goal,
        inputs={},
        output_hash=output_hash,
        proof=proof,
        confidence=0.99,
        cost_usd=0.0,
        latency_ms=0,
        created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )

    # 3. Sign
    ko_dict = ko.to_dict()
    signature = sign_object(ko_dict, pem)
    ko.proof.signature = signature
    ko.id = ko.compute_id()
    print(f"KO ID: {ko.id}")

    # 4. Store
    tmp = tempfile.mkdtemp()
    store = KOLocalStore(path=Path(tmp))
    store.put(ko, output_text.encode())
    print(f"Stored in {tmp}\n")

    # 5. Retrieve and verify
    retrieved = store.get(ko.id)
    assert retrieved is not None

    ok = verify_signature(retrieved.to_dict(), retrieved.proof.signature, retrieved.proof.signer_did)
    print(f"Signature valid: {ok}")
    assert ok

    id_ok = retrieved.compute_id() == ko.id
    print(f"ID integrity:    {id_ok}")
    assert id_ok

    # 6. Search
    store.put(_make_extra_ko(did, pem), b"42")
    results = store.search_by_goal("capital")
    print(f"\nSearch 'capital': {len(results)} result(s)")
    for r in results:
        print(f"  {r.id}  {r.goal}")

    print("\nDemo passed!")


def _make_extra_ko(did, pem):
    goal = "Capital of Germany?"
    output = "Berlin"
    proof = Proof(
        model="demo-model",
        execution_trace_hash=hashlib.sha256(output.encode()).hexdigest(),
        signature="",
        signer_did=did,
    )
    ko = KnowledgeObject(
        goal=goal,
        inputs={},
        output_hash=hashlib.sha3_256(output.encode()).hexdigest(),
        proof=proof,
        created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )
    ko_dict = ko.to_dict()
    ko.proof.signature = sign_object(ko_dict, pem)
    ko.id = ko.compute_id()
    return ko


if __name__ == "__main__":
    demo()

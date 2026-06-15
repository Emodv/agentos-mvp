import hashlib
import json
import time
from typing import Optional

import openai

from .config import get_or_create_identity
from .crypto import sign_object
from .ko import KnowledgeObject, Proof
from .store import KOLocalStore


def execute_and_commit(
    goal: str,
    inputs: dict,
    model: str = "gpt-4-turbo",
    private_key_pem: Optional[str] = None,
    signer_did: Optional[str] = None,
    store: Optional[KOLocalStore] = None,
) -> tuple[KnowledgeObject, str]:
    """Run an LLM call, capture evidence, and commit a KO to local store."""
    if not private_key_pem or not signer_did:
        signer_did, private_key_pem = get_or_create_identity()

    client = openai.OpenAI()
    start = time.time()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": f"Goal: {goal}\nInputs: {json_stable(inputs)}"}],
    )
    latency_ms = int((time.time() - start) * 1000)

    output_text: str = response.choices[0].message.content or ""
    output_hash = hashlib.sha3_256(output_text.encode()).hexdigest()

    usage = response.usage
    cost_usd = 0.0
    if usage:
        cost_usd = round(
            (usage.prompt_tokens * 0.01 + usage.completion_tokens * 0.03) / 1000, 6
        )

    trace_hash = hashlib.sha256(
        f"{goal}{json_stable(inputs)}{output_text}".encode()
    ).hexdigest()

    proof = Proof(
        model=model,
        execution_trace_hash=trace_hash,
        signature="",
        signer_did=signer_did,
    )
    ko = KnowledgeObject(
        goal=goal,
        inputs=inputs,
        output_hash=output_hash,
        proof=proof,
        confidence=0.9,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )

    ko.proof.signature = sign_object(ko.to_dict(), private_key_pem)
    ko.id = ko.compute_id()

    if store is None:
        store = KOLocalStore()
    store.put(ko, output_text.encode())

    return ko, output_text


def json_stable(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))

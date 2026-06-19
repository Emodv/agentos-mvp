import hashlib
import json
import time
from typing import Optional

from .config import get_or_create_identity
from .crypto import sign_object
from .ko import KnowledgeObject, Proof
from .store import KOLocalStore

# Per-1K-token (prompt, completion) USD pricing, used only for the cost_usd estimate
# recorded on the KO -- not an authoritative billing source.
_PRICING = {
    "gpt-4-turbo": (0.01, 0.03),
    "gpt-4o": (0.005, 0.015),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "claude-3-5-sonnet-20241022": (0.003, 0.015),
    "claude-3-5-haiku-20241022": (0.0008, 0.004),
    "claude-3-opus-20240229": (0.015, 0.075),
}
_DEFAULT_PRICING = (0.01, 0.03)


def _is_anthropic_model(model: str) -> bool:
    return model.startswith("claude")


def _run_anthropic(model: str, prompt: str) -> tuple[str, int, int]:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    output_text = "".join(
        block.text for block in response.content if block.type == "text"
    )
    return output_text, response.usage.input_tokens, response.usage.output_tokens


def _run_openai(model: str, prompt: str) -> tuple[str, int, int]:
    import openai

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    output_text = response.choices[0].message.content or ""
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    return output_text, prompt_tokens, completion_tokens


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

    prompt = f"Goal: {goal}\nInputs: {json_stable(inputs)}"
    start = time.time()
    if _is_anthropic_model(model):
        output_text, prompt_tokens, completion_tokens = _run_anthropic(model, prompt)
    else:
        output_text, prompt_tokens, completion_tokens = _run_openai(model, prompt)
    latency_ms = int((time.time() - start) * 1000)

    output_hash = hashlib.sha3_256(output_text.encode()).hexdigest()

    prompt_rate, completion_rate = _PRICING.get(model, _DEFAULT_PRICING)
    cost_usd = round(
        (prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1000, 6
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

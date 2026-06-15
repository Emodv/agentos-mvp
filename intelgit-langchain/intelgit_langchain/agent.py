"""
KOAgent – transparent IntelGit caching layer for any LangChain LLM.

Usage::

    from langchain_openai import ChatOpenAI
    from intelgit_langchain import KOAgent

    llm = ChatOpenAI(model="gpt-4-turbo")
    ko_llm = KOAgent(llm, similarity_threshold=0.90)

    result = ko_llm.invoke("What is the capital of France?")
    # → runs LLM, commits KO

    result2 = ko_llm.invoke("France's capital city?")
    # → cache hit (score 0.95), returns cached output, no LLM call
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Optional, Union

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.outputs import LLMResult

import sys
import os
# Allow importing intelgit when installed as editable from parent dir
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "intelgit"))

from src.core.crypto import generate_did_key, sign_object
from src.core.ko import KnowledgeObject, Proof
from src.core.store import KOLocalStore, REUSE_COST_USD


REUSE_COST_USD = 0.000001


class KOAgent:
    """
    Wraps a LangChain LLM (or chat model) with transparent KO caching.

    On each invocation:
    1. Search local KO store for a semantically similar goal.
    2. If found above `similarity_threshold`, return cached output (no LLM call).
    3. Otherwise, invoke the underlying LLM, commit the result as a new KO.

    No changes to agent logic required — just wrap the LLM.
    """

    def __init__(
        self,
        llm: BaseLanguageModel,
        store_path: Optional[Path] = None,
        similarity_threshold: float = 0.85,
        private_key_pem: Optional[str] = None,
        signer_did: Optional[str] = None,
        registry_url: Optional[str] = None,
    ):
        self.llm = llm
        self.store = KOLocalStore(path=store_path or Path.home() / ".intelgit")
        self.threshold = similarity_threshold
        self.registry_url = registry_url

        if private_key_pem and signer_did:
            self._pem = private_key_pem
            self._did = signer_did
        else:
            self._did, self._pem = generate_did_key()

        # Statistics
        self.stats = {"hits": 0, "misses": 0, "saved_usd": 0.0, "saved_ms": 0}

    # ── Public API ────────────────────────────────────────────────────────────

    def invoke(self, input: Union[str, list[BaseMessage]], **kwargs) -> str:
        """Invoke with transparent KO caching. Returns output text."""
        goal = self._extract_goal(input)
        return self._run(goal, inputs={"raw": goal}, **kwargs)

    def ainvoke(self, input: Union[str, list[BaseMessage]], **kwargs):
        raise NotImplementedError("Use invoke() for now; async support coming soon.")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self, goal: str, inputs: dict, **kwargs) -> str:
        # 1. Cache lookup
        results = self.store.find_similar(goal, top_k=1, threshold=self.threshold)
        if results:
            hit = results[0]
            output = self.store.get_output(hit.ko.id)
            if output is not None:
                self.stats["hits"] += 1
                self.stats["saved_usd"] += hit.ko.cost_usd
                self.stats["saved_ms"] += hit.ko.latency_ms
                return output

        # 2. Cache miss → call LLM
        self.stats["misses"] += 1
        start = time.time()
        raw_output = self._call_llm(goal, **kwargs)
        latency_ms = int((time.time() - start) * 1000)

        # 3. Commit KO
        self._commit(goal, inputs, raw_output, latency_ms)
        return raw_output

    def _call_llm(self, goal: str, **kwargs) -> str:
        result = self.llm.invoke([HumanMessage(content=goal)], **kwargs)
        if hasattr(result, "content"):
            return result.content
        return str(result)

    def _commit(self, goal: str, inputs: dict, output: str, latency_ms: int):
        output_hash = hashlib.sha3_256(output.encode()).hexdigest()
        trace_hash = hashlib.sha256(f"{goal}{output}".encode()).hexdigest()

        proof = Proof(
            model=_model_name(self.llm),
            execution_trace_hash=trace_hash,
            signature="",
            signer_did=self._did,
        )
        ko = KnowledgeObject(
            goal=goal,
            inputs=inputs,
            output_hash=output_hash,
            proof=proof,
            confidence=0.9,
            latency_ms=latency_ms,
        )
        ko_dict = ko.to_dict()
        ko.proof.signature = sign_object(ko_dict, self._pem)
        ko.id = ko.compute_id()
        self.store.put(ko, output.encode())

    @staticmethod
    def _extract_goal(input: Union[str, list]) -> str:
        if isinstance(input, str):
            return input
        for msg in reversed(input):
            if hasattr(msg, "content"):
                return msg.content
        return str(input)

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def print_stats(self):
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = self.stats["hits"] / total * 100 if total else 0
        print(f"KOAgent stats  |  total={total}  hits={self.stats['hits']}  "
              f"hit_rate={hit_rate:.1f}%  "
              f"saved=${self.stats['saved_usd']:.4f}  "
              f"saved_latency={self.stats['saved_ms']}ms")


def _model_name(llm: BaseLanguageModel) -> str:
    return getattr(llm, "model_name", None) or getattr(llm, "model", None) or type(llm).__name__

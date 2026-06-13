from pydantic import BaseModel, Field
from typing import Dict, Any, List
from datetime import datetime, timezone
import hashlib
import json


class Proof(BaseModel):
    model: str
    execution_trace_hash: str
    signature: str
    signer_did: str


class KnowledgeObject(BaseModel):
    id: str = ""
    goal: str
    inputs: Dict[str, Any]
    output_hash: str
    proof: Proof
    dependencies: List[str] = Field(default_factory=list)
    confidence: float = 0.5
    cost_usd: float = 0.0
    latency_ms: int = 0
    license: str = "reuse-with-attribution"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_id(self) -> str:
        """Recompute ID from canonical JSON (without 'id' field)."""
        data = self.model_dump(exclude={"id"})
        # Make datetime JSON-serializable
        data["created_at"] = self.created_at.isoformat()
        data["proof"] = self.proof.model_dump()
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        h = hashlib.sha256(canonical.encode()).hexdigest()
        return f"ko://sha256/{h}"

    def to_dict(self) -> dict:
        data = self.model_dump()
        data["created_at"] = self.created_at.isoformat()
        data["proof"] = self.proof.model_dump()
        return data

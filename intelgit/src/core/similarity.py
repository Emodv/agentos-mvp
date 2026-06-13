"""
Similarity scoring between goal strings.
Primary: sentence-transformers cosine similarity (if installed).
Fallback: Jaccard token overlap.
"""
from __future__ import annotations

import re
from typing import Optional


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def jaccard(a: str, b: str) -> float:
    ta, tb = tokenize(a), tokenize(b)
    if not ta and not tb:
        return 1.0
    return len(ta & tb) / len(ta | tb)


def _cosine_similarity(a, b) -> float:
    import numpy as np
    a, b = np.array(a), np.array(b)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


_encoder = None


def _get_encoder(model: str = "all-MiniLM-L6-v2"):
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer  # type: ignore
        _encoder = SentenceTransformer(model)
    return _encoder


def encode(text: str) -> Optional[list[float]]:
    """Return embedding vector, or None if sentence-transformers unavailable."""
    try:
        enc = _get_encoder()
        return enc.encode(text, normalize_embeddings=True).tolist()
    except ImportError:
        return None


def similarity(query: str, candidate: str, query_vec: Optional[list] = None,
               candidate_vec: Optional[list] = None) -> float:
    """
    Compute similarity in [0, 1].
    Uses embedding cosine similarity when vectors are provided; else Jaccard.
    """
    if query_vec and candidate_vec:
        return max(0.0, _cosine_similarity(query_vec, candidate_vec))
    return jaccard(query, candidate)

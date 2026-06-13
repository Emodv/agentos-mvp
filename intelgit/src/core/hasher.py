"""Semantic hashing utilities (optional, requires sentence-transformers)."""
import hashlib


def semantic_hash(text: str) -> str:
    """SHA3-256 of text as a deterministic content fingerprint."""
    return hashlib.sha3_256(text.encode()).hexdigest()


def embedding_hash(text: str, model: str = "all-MiniLM-L6-v2") -> str:
    """
    Encode text to an embedding vector and hash the quantised bytes.
    Requires: pip install sentence-transformers
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        import numpy as np

        encoder = SentenceTransformer(model)
        vec = encoder.encode(text, normalize_embeddings=True)
        # Quantise to int8 for a stable byte representation
        quantised = (vec * 127).astype(np.int8).tobytes()
        return hashlib.sha256(quantised).hexdigest()
    except ImportError:
        return semantic_hash(text)

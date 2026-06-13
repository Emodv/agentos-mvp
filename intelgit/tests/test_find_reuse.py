"""Tests for find_similar, output caching, and reuse flow."""
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.core.crypto import generate_did_key, sign_object
from src.core.ko import KnowledgeObject, Proof
from src.core.store import KOLocalStore
from src.cli.find import find
from src.cli.reuse import reuse


def _store(tmp_dir: str) -> KOLocalStore:
    return KOLocalStore(path=Path(tmp_dir))


def _commit_ko(store: KOLocalStore, goal: str, output: str, did: str, pem: str) -> KnowledgeObject:
    proof = Proof(
        model="gpt-4-turbo",
        execution_trace_hash=hashlib.sha256(output.encode()).hexdigest(),
        signature="",
        signer_did=did,
    )
    ko = KnowledgeObject(
        goal=goal,
        inputs={},
        output_hash=hashlib.sha3_256(output.encode()).hexdigest(),
        proof=proof,
        confidence=0.95,
        cost_usd=0.001,
        latency_ms=800,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    ko.proof.signature = sign_object(ko.to_dict(), pem)
    ko.id = ko.compute_id()
    store.put(ko, output.encode())
    return ko


@pytest.fixture
def tmp_store(tmp_path):
    return KOLocalStore(path=tmp_path)


@pytest.fixture
def did_pem():
    return generate_did_key()


def test_output_cache_roundtrip(tmp_store, did_pem):
    did, pem = did_pem
    ko = _commit_ko(tmp_store, "Capital of France?", "Paris", did, pem)
    assert tmp_store.get_output(ko.id) == "Paris"


def test_output_cache_missing(tmp_store):
    assert tmp_store.get_output("ko://sha256/doesnotexist") is None


def test_find_similar_jaccard(tmp_store, did_pem):
    did, pem = did_pem
    _commit_ko(tmp_store, "What is the capital of France?", "Paris", did, pem)
    _commit_ko(tmp_store, "Explain quantum computing", "Quantum bits…", did, pem)

    results = tmp_store.find_similar("capital of France", threshold=0.1)
    assert len(results) >= 1
    assert any("France" in r.ko.goal for r in results)
    # scores should be in descending order
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_find_similar_returns_empty_below_threshold(tmp_store, did_pem):
    did, pem = did_pem
    _commit_ko(tmp_store, "Stock market analysis", "Stocks…", did, pem)
    results = tmp_store.find_similar("vegan recipes", threshold=0.99)
    assert results == []


def test_find_cli_no_results(tmp_path):
    runner = CliRunner()
    # Monkey-patch store path via env is hard; use isolation instead
    with runner.isolated_filesystem():
        import os, sys
        # Point store to empty temp dir
        from unittest.mock import patch
        with patch("src.cli.find.KOLocalStore") as MockStore:
            MockStore.return_value.find_similar.return_value = []
            result = runner.invoke(find, ["anything"])
            assert result.exit_code == 0
            assert "No matching" in result.output


def test_reuse_cli_success(tmp_path, did_pem):
    did, pem = did_pem
    store = KOLocalStore(path=tmp_path)
    ko = _commit_ko(store, "Capital of France?", "Paris", did, pem)

    runner = CliRunner()
    from unittest.mock import patch
    with patch("src.cli.reuse.KOLocalStore") as MockStore:
        MockStore.return_value.get.return_value = ko
        MockStore.return_value.get_output.return_value = "Paris"
        result = runner.invoke(reuse, [ko.id])
        assert result.exit_code == 0
        assert "Paris" in result.output


def test_reuse_cli_missing_ko(tmp_path):
    runner = CliRunner()
    from unittest.mock import patch
    with patch("src.cli.reuse.KOLocalStore") as MockStore:
        MockStore.return_value.get.return_value = None
        result = runner.invoke(reuse, ["ko://sha256/nonexistent"])
        assert result.exit_code != 0

from datetime import datetime, timezone

from src.core.ko import KnowledgeObject, Proof


def _make_ko(**kwargs) -> KnowledgeObject:
    defaults = dict(
        goal="Test goal",
        inputs={"key": "value"},
        output_hash="abc123",
        proof=Proof(
            model="gpt-4-turbo",
            execution_trace_hash="trace_hash",
            signature="sig",
            signer_did="did:key:zABC",
        ),
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return KnowledgeObject(**defaults)


def test_compute_id_is_deterministic():
    ko = _make_ko()
    id1 = ko.compute_id()
    id2 = ko.compute_id()
    assert id1 == id2
    assert id1.startswith("ko://sha256/")


def test_compute_id_changes_with_goal():
    ko1 = _make_ko(goal="Goal A")
    ko2 = _make_ko(goal="Goal B")
    assert ko1.compute_id() != ko2.compute_id()


def test_to_dict_contains_expected_keys():
    ko = _make_ko()
    d = ko.to_dict()
    for key in ("goal", "inputs", "output_hash", "proof", "created_at"):
        assert key in d


def test_default_confidence():
    ko = _make_ko()
    assert 0.0 <= ko.confidence <= 1.0

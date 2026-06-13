import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.core.ko import KnowledgeObject, Proof
from src.core.store import KOLocalStore


def _make_store() -> KOLocalStore:
    tmp = tempfile.mkdtemp()
    return KOLocalStore(path=Path(tmp))


def _make_ko(goal: str = "Test", ko_id: str = "ko://sha256/test123") -> KnowledgeObject:
    return KnowledgeObject(
        id=ko_id,
        goal=goal,
        inputs={},
        output_hash="out_hash",
        proof=Proof(
            model="gpt-4-turbo",
            execution_trace_hash="trace",
            signature="sig",
            signer_did="did:key:zABC",
        ),
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def test_put_and_get_roundtrip():
    store = _make_store()
    ko = _make_ko()
    store.put(ko)
    retrieved = store.get(ko.id)
    assert retrieved is not None
    assert retrieved.id == ko.id
    assert retrieved.goal == ko.goal


def test_get_missing_returns_none():
    store = _make_store()
    assert store.get("ko://sha256/nonexistent") is None


def test_search_by_goal():
    store = _make_store()
    store.put(_make_ko(goal="Capital of France", ko_id="ko://sha256/a1"))
    store.put(_make_ko(goal="Capital of Germany", ko_id="ko://sha256/a2"))
    store.put(_make_ko(goal="Quantum computing basics", ko_id="ko://sha256/a3"))

    results = store.search_by_goal("Capital")
    assert len(results) == 2

    results2 = store.search_by_goal("Quantum")
    assert len(results2) == 1


def test_list_all():
    store = _make_store()
    for i in range(3):
        store.put(_make_ko(goal=f"Goal {i}", ko_id=f"ko://sha256/{i}"))
    all_kos = store.list_all(limit=10)
    assert len(all_kos) == 3


def test_put_upsert():
    store = _make_store()
    ko = _make_ko()
    store.put(ko)
    ko.goal = "Updated goal"
    store.put(ko)
    retrieved = store.get(ko.id)
    assert retrieved.goal == "Updated goal"

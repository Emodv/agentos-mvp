import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, NamedTuple

from .ko import KnowledgeObject, Proof


class ScoredKO(NamedTuple):
    ko: KnowledgeObject
    score: float


class KOLocalStore:
    def __init__(self, path: Path = Path.home() / ".intelgit"):
        self.path = path
        self.path.mkdir(exist_ok=True)
        self.db_path = self.path / "index.db"
        (self.path / "outputs").mkdir(exist_ok=True)
        self._init_db()
        self._ipfs = None

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kos (
                id          TEXT PRIMARY KEY,
                goal        TEXT,
                inputs      TEXT,
                output_hash TEXT,
                proof       TEXT,
                dependencies TEXT,
                confidence  REAL,
                cost_usd    REAL,
                latency_ms  INTEGER,
                license     TEXT,
                created_at  TEXT,
                ipfs_cid    TEXT,
                goal_vec    TEXT
            )
        """)
        # Migrate: add goal_vec column to existing DBs if missing
        cols = [r[1] for r in conn.execute("PRAGMA table_info(kos)").fetchall()]
        if "goal_vec" not in cols:
            conn.execute("ALTER TABLE kos ADD COLUMN goal_vec TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_goal ON kos(goal)")
        conn.commit()
        conn.close()

    # ── IPFS ──────────────────────────────────────────────────────────────────

    def _get_ipfs(self):
        if self._ipfs is None:
            try:
                import ipfshttpclient  # type: ignore
                self._ipfs = ipfshttpclient.connect("/ip4/127.0.0.1/tcp/5001")
            except Exception:
                self._ipfs = False
        return self._ipfs if self._ipfs else None

    # ── Write ─────────────────────────────────────────────────────────────────

    def put(self, ko: KnowledgeObject, output_bytes: Optional[bytes] = None) -> Optional[str]:
        cid = None
        if output_bytes:
            # Local output cache (always)
            self._write_output(ko.id, output_bytes)
            # IPFS (optional)
            ipfs = self._get_ipfs()
            if ipfs:
                try:
                    cid = ipfs.add_bytes(output_bytes)
                except Exception:
                    pass

        # Embed goal for semantic search (optional)
        goal_vec = None
        try:
            from .similarity import encode
            vec = encode(ko.goal)
            if vec is not None:
                goal_vec = json.dumps(vec)
        except Exception:
            pass

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO kos
            (id, goal, inputs, output_hash, proof, dependencies,
             confidence, cost_usd, latency_ms, license, created_at, ipfs_cid, goal_vec)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ko.id,
            ko.goal,
            json.dumps(ko.inputs),
            ko.output_hash,
            json.dumps(ko.proof.model_dump()),
            json.dumps(ko.dependencies),
            ko.confidence,
            ko.cost_usd,
            ko.latency_ms,
            ko.license,
            ko.created_at.isoformat(),
            cid,
            goal_vec,
        ))
        conn.commit()
        conn.close()
        return cid

    def _write_output(self, ko_id: str, data: bytes):
        (self.path / "outputs" / self._safe_name(ko_id)).write_bytes(data)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, ko_id: str) -> Optional[KnowledgeObject]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT * FROM kos WHERE id = ?", (ko_id,))
        row = cur.fetchone()
        conn.close()
        return self._row_to_ko(row) if row else None

    def get_output(self, ko_id: str) -> Optional[str]:
        """Return cached output text, or None if not available locally."""
        p = self.path / "outputs" / self._safe_name(ko_id)
        return p.read_text(errors="replace") if p.exists() else None

    def search_by_goal(self, query: str, top_k: int = 5) -> List[KnowledgeObject]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT * FROM kos WHERE goal LIKE ? LIMIT ?",
            (f"%{query}%", top_k),
        )
        rows = cur.fetchall()
        conn.close()
        return [self._row_to_ko(r) for r in rows]

    def find_similar(self, query: str, top_k: int = 5,
                     threshold: float = 0.5) -> List[ScoredKO]:
        """
        Return KOs whose goal is semantically similar to `query`.
        Uses embedding cosine similarity when goal_vec is stored, else Jaccard.
        Results are sorted by score descending and filtered by threshold.
        """
        from .similarity import encode, similarity as score_fn

        query_vec = encode(query)  # None if sentence-transformers unavailable

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT * FROM kos").fetchall()
        conn.close()

        scored: List[ScoredKO] = []
        for row in rows:
            ko = self._row_to_ko(row)
            candidate_vec = None
            if query_vec is not None and row[12]:  # goal_vec column
                try:
                    candidate_vec = json.loads(row[12])
                except Exception:
                    pass
            s = score_fn(query, ko.goal, query_vec, candidate_vec)
            if s >= threshold:
                scored.append(ScoredKO(ko=ko, score=round(s, 4)))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def list_all(self, limit: int = 20) -> List[KnowledgeObject]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT * FROM kos ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = cur.fetchall()
        conn.close()
        return [self._row_to_ko(r) for r in rows]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_name(ko_id: str) -> str:
        return ko_id.replace("ko://", "").replace("/", "_")

    @staticmethod
    def _row_to_ko(row) -> KnowledgeObject:
        (
            id_, goal, inputs, output_hash, proof_json,
            deps, confidence, cost_usd, latency_ms,
            license_, created_at, _ipfs_cid,
            *_rest,  # goal_vec (may be absent in old DBs)
        ) = row
        return KnowledgeObject(
            id=id_,
            goal=goal,
            inputs=json.loads(inputs),
            output_hash=output_hash,
            proof=Proof(**json.loads(proof_json)),
            dependencies=json.loads(deps),
            confidence=confidence,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            license=license_,
            created_at=datetime.fromisoformat(created_at),
        )

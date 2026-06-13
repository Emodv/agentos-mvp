import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from .ko import KnowledgeObject, Proof


class KOLocalStore:
    def __init__(self, path: Path = Path.home() / ".intelgit"):
        self.path = path
        self.path.mkdir(exist_ok=True)
        self.db_path = self.path / "index.db"
        self._init_db()
        self._ipfs = None  # lazy-loaded

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
                ipfs_cid    TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_goal ON kos(goal)")
        conn.commit()
        conn.close()

    def _get_ipfs(self):
        if self._ipfs is None:
            try:
                import ipfshttpclient  # optional dependency
                self._ipfs = ipfshttpclient.connect("/ip4/127.0.0.1/tcp/5001")
            except Exception:
                self._ipfs = False  # mark as unavailable
        return self._ipfs if self._ipfs else None

    def put(self, ko: KnowledgeObject, output_bytes: Optional[bytes] = None) -> Optional[str]:
        cid = None
        if output_bytes:
            ipfs = self._get_ipfs()
            if ipfs:
                try:
                    cid = ipfs.add_bytes(output_bytes)
                except Exception:
                    pass
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO kos
            (id, goal, inputs, output_hash, proof, dependencies,
             confidence, cost_usd, latency_ms, license, created_at, ipfs_cid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ))
        conn.commit()
        conn.close()
        return cid

    def get(self, ko_id: str) -> Optional[KnowledgeObject]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT * FROM kos WHERE id = ?", (ko_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_ko(row)

    def search_by_goal(self, query: str, top_k: int = 5) -> List[KnowledgeObject]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT * FROM kos WHERE goal LIKE ? LIMIT ?",
            (f"%{query}%", top_k),
        )
        rows = cur.fetchall()
        conn.close()
        return [self._row_to_ko(r) for r in rows]

    def list_all(self, limit: int = 20) -> List[KnowledgeObject]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT * FROM kos ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = cur.fetchall()
        conn.close()
        return [self._row_to_ko(r) for r in rows]

    @staticmethod
    def _row_to_ko(row) -> KnowledgeObject:
        (
            id_, goal, inputs, output_hash, proof_json,
            deps, confidence, cost_usd, latency_ms,
            license_, created_at, _ipfs_cid,
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

"""SQLite-backed registry store."""
import json
import sqlite3
from pathlib import Path
from typing import Optional

DATA_DIR = Path("/data/intelgit")


def get_data_dir() -> Path:
    import os
    p = Path(os.environ.get("INTELGIT_DATA", DATA_DIR))
    p.mkdir(parents=True, exist_ok=True)
    (p / "outputs").mkdir(exist_ok=True)
    return p


def get_conn() -> sqlite3.Connection:
    db = get_data_dir() / "registry.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id           TEXT PRIMARY KEY,
            display_name TEXT,
            api_key_hash TEXT UNIQUE NOT NULL,
            credits      REAL DEFAULT 1000,
            created_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS kos (
            id           TEXT PRIMARY KEY,
            goal         TEXT NOT NULL,
            inputs       TEXT,
            output_hash  TEXT,
            proof        TEXT,
            dependencies TEXT,
            confidence   REAL,
            cost_usd     REAL,
            latency_ms   INTEGER,
            license      TEXT,
            created_at   TEXT,
            signer_did   TEXT,
            creator_id   TEXT,
            reuse_count  INTEGER DEFAULT 0,
            pushed_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_goal     ON kos(goal);
        CREATE INDEX IF NOT EXISTS idx_signer   ON kos(signer_did);
        CREATE INDEX IF NOT EXISTS idx_creator  ON kos(creator_id);

        CREATE TABLE IF NOT EXISTS packages (
            name         TEXT PRIMARY KEY,
            latest_ko_id TEXT NOT NULL,
            owner_id     TEXT,
            description  TEXT,
            created_at   TEXT DEFAULT (datetime('now')),
            updated_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS payments (
            id          TEXT PRIMARY KEY,
            from_agent  TEXT,
            to_agent    TEXT,
            ko_id       TEXT,
            amount_msat INTEGER,
            status      TEXT,
            tx_id       TEXT,
            created_at  TEXT
        );
    """)
    conn.commit()
    conn.close()


# ── KOs ───────────────────────────────────────────────────────────────────────

def upsert_ko(ko: dict, creator_id: Optional[str] = None):
    proof = ko.get("proof", {})
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO kos
        (id, goal, inputs, output_hash, proof, dependencies,
         confidence, cost_usd, latency_ms, license, created_at, signer_did, creator_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ko["id"],
        ko["goal"],
        json.dumps(ko.get("inputs", {})),
        ko.get("output_hash", ""),
        json.dumps(proof),
        json.dumps(ko.get("dependencies", [])),
        ko.get("confidence", 0.5),
        ko.get("cost_usd", 0.0),
        ko.get("latency_ms", 0),
        ko.get("license", "reuse-with-attribution"),
        ko.get("created_at", ""),
        proof.get("signer_did", "") if isinstance(proof, dict) else "",
        creator_id,
    ))
    conn.commit()
    conn.close()


def fetch_ko(ko_id: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM kos WHERE id = ?", (ko_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def increment_reuse(ko_id: str):
    conn = get_conn()
    conn.execute("UPDATE kos SET reuse_count = reuse_count + 1 WHERE id = ?", (ko_id,))
    conn.commit()
    conn.close()


def search_kos(query: str, top_k: int = 10) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM kos WHERE goal LIKE ? ORDER BY reuse_count DESC LIMIT ?",
        (f"%{query}%", top_k),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def top_kos(limit: int = 20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM kos ORDER BY reuse_count DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def leaderboard(limit: int = 20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT signer_did,
               COUNT(*)         AS ko_count,
               SUM(reuse_count) AS total_reuses
        FROM kos
        GROUP BY signer_did
        ORDER BY total_reuses DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def recent_kos(limit: int = 20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM kos ORDER BY pushed_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Packages ──────────────────────────────────────────────────────────────────

def upsert_package(name: str, ko_id: str, owner_id: str, description: str = ""):
    conn = get_conn()
    conn.execute("""
        INSERT INTO packages (name, latest_ko_id, owner_id, description)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            latest_ko_id = excluded.latest_ko_id,
            description  = excluded.description,
            updated_at   = datetime('now')
        WHERE owner_id = excluded.owner_id
    """, (name, ko_id, owner_id, description))
    conn.commit()
    conn.close()


def fetch_package(name: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM packages WHERE name = ?", (name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_packages(limit: int = 50) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM packages ORDER BY updated_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Output storage ────────────────────────────────────────────────────────────

def _output_path(ko_id: str) -> Path:
    safe = ko_id.replace("ko://", "").replace("/", "_")
    return get_data_dir() / "outputs" / safe


def save_output(ko_id: str, data: bytes):
    _output_path(ko_id).write_bytes(data)


def load_output(ko_id: str) -> Optional[bytes]:
    p = _output_path(ko_id)
    return p.read_bytes() if p.exists() else None

"""Sales tracking dashboard for IntelGit outreach agent."""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask, render_template, jsonify

DB_PATH = Path(__file__).parent.parent / "scripts" / "contacts.db"

app = Flask(__name__)


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _stats() -> dict:
    if not DB_PATH.exists():
        return _empty_stats()

    conn = _get_db()
    try:
        cur = conn.cursor()

        # Total prospects
        cur.execute("SELECT COUNT(*) FROM prospects")
        total_prospects = cur.fetchone()[0]

        # Total outreach
        cur.execute("SELECT COUNT(*) FROM outreach_log")
        total_outreach = cur.fetchone()[0]

        # By platform
        cur.execute("""
            SELECT platform, COUNT(*) as cnt
            FROM outreach_log
            GROUP BY platform
            ORDER BY cnt DESC
        """)
        by_platform = {row["platform"]: row["cnt"] for row in cur.fetchall()}

        # By status
        cur.execute("""
            SELECT status, COUNT(*) as cnt
            FROM prospects
            GROUP BY status
        """)
        by_status = {row["status"]: row["cnt"] for row in cur.fetchall()}

        # Daily outreach (last 14 days)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        cur.execute("""
            SELECT DATE(sent_at) as day, COUNT(*) as cnt
            FROM outreach_log
            WHERE sent_at >= ?
            GROUP BY day
            ORDER BY day
        """, (cutoff,))
        daily = [{"date": row["day"], "count": row["cnt"]} for row in cur.fetchall()]

        # Conversion funnel
        funnel = [
            {"stage": "Identified",  "count": total_prospects},
            {"stage": "Contacted",   "count": total_outreach},
            {"stage": "Responded",   "count": by_status.get("responded", 0)},
            {"stage": "Converted",   "count": by_status.get("converted", 0)},
        ]

        # Recent activity (last 20 actions)
        cur.execute("""
            SELECT o.platform, o.action, o.sent_at, p.username, p.repo_url
            FROM outreach_log o
            LEFT JOIN prospects p ON o.prospect_id = p.id
            ORDER BY o.sent_at DESC
            LIMIT 20
        """)
        recent = [dict(row) for row in cur.fetchall()]

        # Top repos by interest
        cur.execute("""
            SELECT p.repo_url, p.username, p.platform, COUNT(o.id) as touches
            FROM prospects p
            LEFT JOIN outreach_log o ON o.prospect_id = p.id
            GROUP BY p.id
            ORDER BY touches DESC
            LIMIT 10
        """)
        top_repos = [dict(row) for row in cur.fetchall()]

        return {
            "total_prospects": total_prospects,
            "total_outreach": total_outreach,
            "by_platform": by_platform,
            "by_status": by_status,
            "daily": daily,
            "funnel": funnel,
            "recent": recent,
            "top_repos": top_repos,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


def _empty_stats() -> dict:
    return {
        "total_prospects": 0,
        "total_outreach": 0,
        "by_platform": {},
        "by_status": {},
        "daily": [],
        "funnel": [
            {"stage": "Identified", "count": 0},
            {"stage": "Contacted",  "count": 0},
            {"stage": "Responded",  "count": 0},
            {"stage": "Converted",  "count": 0},
        ],
        "recent": [],
        "top_repos": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.route("/")
def index():
    stats = _stats()
    return render_template("index.html", stats=stats, stats_json=json.dumps(stats))


@app.route("/api/stats")
def api_stats():
    return jsonify(_stats())


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5555))
    app.run(host="0.0.0.0", port=port, debug=True)

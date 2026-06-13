"""
IntelGit Hub – public registry for Knowledge Objects.

API endpoints:
  POST /v1/register              Create account → {user_id, api_key}
  GET  /v1/whoami                Current user (auth required)
  POST /v1/ko                    Push KO + output (auth required)
  GET  /v1/ko/{ko_id}            Get KO metadata (public)
  GET  /v1/output/{ko_id}        Download output bytes (public)
  POST /v1/reuse/{ko_id}         Record reuse (public)
  GET  /v1/search?q=             Search by goal text (public)
  GET  /v1/top                   Most-reused KOs (public)
  GET  /v1/leaderboard           Top contributors (public)
  GET  /v1/packages              List packages (public)
  GET  /v1/packages/{name}       Resolve package → KO (public)
  POST /v1/packages              Create/update package alias (auth)
  GET  /v1/balance               Credit balance (auth)
  POST /v1/deposit               Add credits (auth)

Web dashboard:
  GET  /                         Recent KOs
  GET  /ko/{ko_id}               KO detail page
  GET  /leaderboard              Top contributors
  GET  /packages                 Browse packages
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from .auth import create_user, get_user_by_key, require_auth, optional_auth
from .db import (
    init_db, upsert_ko, fetch_ko, search_kos, top_kos, leaderboard,
    recent_kos, save_output, load_output, increment_reuse,
    upsert_package, fetch_package, list_packages,
)
from .payments import provider as payment_provider
from .verify import verify_ko, verify_output


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="IntelGit Hub",
    description="Public registry for verifiable Knowledge Objects (ko://)",
    version="0.2.0",
    lifespan=lifespan,
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    display_name: str = "anonymous"


class RegisterResponse(BaseModel):
    user_id: str
    api_key: str
    credits: int = 1000


class PushResponse(BaseModel):
    id: str
    verified: bool
    message: str


class PackageRequest(BaseModel):
    name: str
    ko_id: str
    description: str = ""


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/v1/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest):
    """Create an account and receive an API key."""
    user_id, raw_key = create_user(body.display_name)
    return RegisterResponse(user_id=user_id, api_key=raw_key)


@app.get("/v1/whoami")
async def whoami(user: dict = Depends(require_auth)):
    return {
        "user_id": user["id"],
        "display_name": user["display_name"],
        "credits": user["credits"],
    }


# ── KOs ───────────────────────────────────────────────────────────────────────

@app.post("/v1/ko", response_model=PushResponse, status_code=201)
async def push_ko(
    ko_json: str = Form(...),
    output: Optional[UploadFile] = File(None),
    user: dict = Depends(require_auth),
):
    """Push a new Knowledge Object. Requires X-API-Key header."""
    try:
        ko = json.loads(ko_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"Invalid KO JSON: {exc}")

    valid, reason = verify_ko(ko)
    if not valid:
        raise HTTPException(400, f"KO verification failed: {reason}")

    output_bytes: Optional[bytes] = None
    if output:
        output_bytes = await output.read()
        if not verify_output(ko, output_bytes):
            raise HTTPException(400, "Output hash mismatch")

    upsert_ko(ko, creator_id=user["id"])
    if output_bytes:
        save_output(ko["id"], output_bytes)

    return PushResponse(id=ko["id"], verified=True, message="KO stored successfully")


@app.get("/v1/ko/{ko_id:path}")
async def get_ko(ko_id: str):
    ko = fetch_ko(ko_id)
    if not ko:
        raise HTTPException(404, f"KO not found: {ko_id}")
    _parse_json_fields(ko)
    return ko


@app.get("/v1/output/{ko_id:path}")
async def get_output(ko_id: str):
    ko = fetch_ko(ko_id)
    if not ko:
        raise HTTPException(404, f"KO not found: {ko_id}")
    data = load_output(ko_id)
    if data is None:
        raise HTTPException(404, "Output not stored on this registry")
    increment_reuse(ko_id)
    return Response(content=data, media_type="text/plain; charset=utf-8")


@app.post("/v1/reuse/{ko_id:path}")
async def record_reuse(ko_id: str):
    ko = fetch_ko(ko_id)
    if not ko:
        raise HTTPException(404, f"KO not found: {ko_id}")
    increment_reuse(ko_id)
    return {"ok": True}


# ── Search & discovery ────────────────────────────────────────────────────────

@app.get("/v1/search")
async def search(
    q: str = Query(...),
    top_k: int = Query(10, ge=1, le=100),
):
    results = search_kos(q, top_k=top_k)
    [_parse_json_fields(r) for r in results]
    return {"query": q, "count": len(results), "results": results}


@app.get("/v1/top")
async def top(limit: int = Query(20, ge=1, le=100)):
    results = top_kos(limit=limit)
    [_parse_json_fields(r) for r in results]
    return {"results": results}


@app.get("/v1/leaderboard")
async def get_leaderboard(limit: int = Query(20, ge=1, le=100)):
    return {"results": leaderboard(limit=limit)}


# ── Packages ──────────────────────────────────────────────────────────────────

@app.get("/v1/packages")
async def get_packages():
    return {"results": list_packages()}


@app.get("/v1/packages/{name:path}")
async def get_package(name: str):
    pkg = fetch_package(name)
    if not pkg:
        raise HTTPException(404, f"Package not found: {name}")
    ko = fetch_ko(pkg["latest_ko_id"])
    if ko:
        _parse_json_fields(ko)
    return {"package": pkg, "ko": ko}


@app.post("/v1/packages", status_code=201)
async def create_package(body: PackageRequest, user: dict = Depends(require_auth)):
    ko = fetch_ko(body.ko_id)
    if not ko:
        raise HTTPException(404, f"KO not found: {body.ko_id}")
    upsert_package(body.name, body.ko_id, user["id"], body.description)
    return {"ok": True, "name": body.name}


# ── Payments ──────────────────────────────────────────────────────────────────

@app.get("/v1/balance")
async def balance(user: dict = Depends(require_auth)):
    bal = payment_provider().get_balance(user["id"])
    return {"user_id": user["id"], "balance_msat": bal, "balance_credits": user["credits"]}


@app.post("/v1/deposit")
async def deposit(amount_usd: float = Query(..., gt=0), user: dict = Depends(require_auth)):
    amount_msat = int(amount_usd * 100_000_000)  # rough conversion
    tx = payment_provider().deposit(user["id"], amount_msat)
    return {"ok": True, "tx_id": tx, "amount_msat": amount_msat}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Web dashboard (HTML) ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard_home():
    kos = recent_kos(limit=20)
    rows = "".join(
        f"<tr><td><a href='/ko/{r['id']}'>{r['id'][:24]}…</a></td>"
        f"<td>{r['goal'][:60]}</td><td>{r['reuse_count']}</td>"
        f"<td>{r['confidence']:.2f}</td></tr>"
        for r in kos
    )
    return HTMLResponse(_page(
        "IntelGit Hub – Recent KOs",
        f"""
        <h2>Recent Knowledge Objects</h2>
        <table>
          <thead><tr><th>ID</th><th>Goal</th><th>Reuses</th><th>Confidence</th></tr></thead>
          <tbody>{rows or '<tr><td colspan=4>No KOs yet.</td></tr>'}</tbody>
        </table>
        <p style="margin-top:1rem">
          <a href='/leaderboard'>Leaderboard</a> &nbsp;|&nbsp;
          <a href='/packages'>Packages</a>
        </p>
        """,
    ))


@app.get("/ko/{ko_id:path}", response_class=HTMLResponse)
async def dashboard_ko(ko_id: str):
    ko = fetch_ko(ko_id)
    if not ko:
        raise HTTPException(404)
    _parse_json_fields(ko)
    output_text = (load_output(ko_id) or b"(output not stored)").decode(errors="replace")
    proof = ko.get("proof") or {}
    return HTMLResponse(_page(
        f"KO – {ko['goal'][:40]}",
        f"""
        <h2>{ko['goal']}</h2>
        <table>
          <tr><th>ID</th><td><code>{ko['id']}</code></td></tr>
          <tr><th>Model</th><td>{proof.get('model','?')}</td></tr>
          <tr><th>Confidence</th><td>{ko['confidence']}</td></tr>
          <tr><th>Cost</th><td>${ko['cost_usd']:.6f}</td></tr>
          <tr><th>Latency</th><td>{ko['latency_ms']}ms</td></tr>
          <tr><th>Reuses</th><td>{ko['reuse_count']}</td></tr>
          <tr><th>License</th><td>{ko['license']}</td></tr>
          <tr><th>Signer DID</th><td><code>{ko.get('signer_did','?')[:40]}…</code></td></tr>
        </table>
        <h3>Output</h3>
        <pre>{output_text[:2000]}</pre>
        <p><a href='/'>← Back</a></p>
        """,
    ))


@app.get("/leaderboard", response_class=HTMLResponse)
async def dashboard_leaderboard():
    rows_data = leaderboard(limit=20)
    rows = "".join(
        f"<tr><td>{i+1}</td><td><code>{r['signer_did'][:32]}…</code></td>"
        f"<td>{r['ko_count']}</td><td>{r['total_reuses'] or 0}</td></tr>"
        for i, r in enumerate(rows_data)
    )
    return HTMLResponse(_page(
        "IntelGit Hub – Leaderboard",
        f"""
        <h2>Top Contributors</h2>
        <table>
          <thead><tr><th>#</th><th>DID</th><th>KOs</th><th>Total Reuses</th></tr></thead>
          <tbody>{rows or '<tr><td colspan=4>No contributors yet.</td></tr>'}</tbody>
        </table>
        <p><a href='/'>← Back</a></p>
        """,
    ))


@app.get("/packages", response_class=HTMLResponse)
async def dashboard_packages():
    pkgs = list_packages()
    rows = "".join(
        f"<tr><td><code>{p['name']}</code></td>"
        f"<td><a href='/ko/{p['latest_ko_id']}'>{p['latest_ko_id'][:24]}…</a></td>"
        f"<td>{p.get('description','')[:60]}</td></tr>"
        for p in pkgs
    )
    return HTMLResponse(_page(
        "IntelGit Hub – Packages",
        f"""
        <h2>Packages</h2>
        <table>
          <thead><tr><th>Name</th><th>Latest KO</th><th>Description</th></tr></thead>
          <tbody>{rows or '<tr><td colspan=3>No packages yet.</td></tr>'}</tbody>
        </table>
        <p><a href='/'>← Back</a></p>
        """,
    ))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_json_fields(d: dict):
    for field in ("inputs", "proof", "dependencies"):
        if isinstance(d.get(field), str):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                pass


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
  <style>
    body {{ max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
    pre {{ background:#f4f4f4; padding:1rem; overflow-x:auto; }}
    th {{ text-align:left; }}
  </style>
</head>
<body>
  <header><h1><a href="/" style="text-decoration:none">🧠 IntelGit Hub</a></h1>
  <nav><a href="/v1/search?q=">API</a> | <a href="/docs">OpenAPI</a></nav></header>
  <main>{body}</main>
  <footer><small>IntelGit – Git for Intelligence</small></footer>
</body>
</html>"""


def start():
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    start()

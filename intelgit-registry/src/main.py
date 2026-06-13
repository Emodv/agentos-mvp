"""
IntelGit Hub – public registry server for Knowledge Objects.

Endpoints:
  POST /v1/ko                  Push a new KO (+ output bytes in multipart)
  GET  /v1/ko/{ko_id}          Retrieve KO metadata
  GET  /v1/output/{ko_id}      Retrieve raw output bytes
  GET  /v1/search?q=<query>    Search KOs by goal text
  GET  /v1/top                 Most-reused KOs
  GET  /v1/leaderboard         Top contributors by total reuses
  POST /v1/reuse/{ko_id}       Record a reuse event (increment counter)
  GET  /health                 Liveness probe
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from .db import (
    init_db, upsert_ko, fetch_ko, search_kos, top_kos, leaderboard,
    save_output, load_output, increment_reuse,
)
from .verify import verify_ko, verify_output


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="IntelGit Hub",
    description="Public registry for verifiable Knowledge Objects (ko://)",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Models ────────────────────────────────────────────────────────────────────

class PushResponse(BaseModel):
    id: str
    verified: bool
    message: str


class KOSummary(BaseModel):
    id: str
    goal: str
    confidence: float
    reuse_count: int
    license: str
    signer_did: str


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/ko", response_model=PushResponse, status_code=201)
async def push_ko(
    ko_json: str = Form(..., description="KO metadata as JSON string"),
    output: Optional[UploadFile] = File(None, description="Raw output bytes"),
):
    """Push a new Knowledge Object to the registry."""
    try:
        ko = json.loads(ko_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"Invalid KO JSON: {exc}")

    # Verify integrity
    valid, reason = verify_ko(ko)
    if not valid:
        raise HTTPException(400, f"KO verification failed: {reason}")

    # Verify output hash (if output provided)
    output_bytes: Optional[bytes] = None
    if output:
        output_bytes = await output.read()
        if not verify_output(ko, output_bytes):
            raise HTTPException(400, "Output hash mismatch")

    # Persist
    upsert_ko(ko)
    if output_bytes:
        save_output(ko["id"], output_bytes)

    return PushResponse(id=ko["id"], verified=True, message="KO stored successfully")


@app.get("/v1/ko/{ko_id:path}")
async def get_ko(ko_id: str):
    """Retrieve KO metadata by ID."""
    ko = fetch_ko(ko_id)
    if not ko:
        raise HTTPException(404, f"KO not found: {ko_id}")
    # Parse JSON fields back
    for field in ("inputs", "proof", "dependencies"):
        if isinstance(ko.get(field), str):
            try:
                ko[field] = json.loads(ko[field])
            except Exception:
                pass
    return ko


@app.get("/v1/output/{ko_id:path}")
async def get_output(ko_id: str):
    """Retrieve the raw output bytes for a KO (GET /v1/output/<ko_id>)."""
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
    """Increment reuse counter (POST /v1/reuse/<ko_id>)."""
    ko = fetch_ko(ko_id)
    if not ko:
        raise HTTPException(404, f"KO not found: {ko_id}")
    increment_reuse(ko_id)
    return {"ok": True}


@app.get("/v1/search")
async def search(
    q: str = Query(..., description="Goal text query"),
    top_k: int = Query(10, ge=1, le=100),
):
    """Search KOs by goal text (full-text substring, ranked by reuse count)."""
    results = search_kos(q, top_k=top_k)
    return {"query": q, "count": len(results), "results": results}


@app.get("/v1/top")
async def top(limit: int = Query(20, ge=1, le=100)):
    """Most-reused Knowledge Objects."""
    return {"results": top_kos(limit=limit)}


@app.get("/v1/leaderboard")
async def get_leaderboard(limit: int = Query(20, ge=1, le=100)):
    """Top contributors ranked by total reuses of their KOs."""
    return {"results": leaderboard(limit=limit)}


def start():
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    start()

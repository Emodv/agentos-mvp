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
    init_db, get_conn, upsert_ko, fetch_ko, search_kos, top_kos, leaderboard,
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


@app.get("/v1/stats")
async def stats():
    """Aggregate registry statistics for the marketing dashboard."""
    conn = get_conn()
    total_kos = conn.execute("SELECT COUNT(*) FROM kos").fetchone()[0]
    total_reuses = conn.execute("SELECT COALESCE(SUM(reuse_count), 0) FROM kos").fetchone()[0]
    unique_agents = conn.execute("SELECT COUNT(DISTINCT signer_did) FROM kos").fetchone()[0]
    total_cost_saved = conn.execute(
        "SELECT COALESCE(SUM(cost_usd * reuse_count), 0) FROM kos"
    ).fetchone()[0]
    total_ms_saved = conn.execute(
        "SELECT COALESCE(SUM(latency_ms * reuse_count), 0) FROM kos"
    ).fetchone()[0]
    top_ko = conn.execute(
        "SELECT id, goal, reuse_count FROM kos ORDER BY reuse_count DESC LIMIT 1"
    ).fetchone()
    conn.close()

    return {
        "total_kos": total_kos,
        "total_reuses": total_reuses,
        "unique_agents": unique_agents,
        "total_cost_saved_usd": round(total_cost_saved, 6),
        "total_latency_saved_ms": int(total_ms_saved),
        "top_ko": dict(top_ko) if top_ko else None,
    }


@app.get("/.well-known/ai-plugin.json")
async def ai_plugin():
    """OpenAI plugin manifest for agent auto-discovery."""
    base = os.environ.get("REGISTRY_BASE_URL", "https://hub.intelgit.ai")
    return {
        "schema_version": "v1",
        "name_for_human": "IntelGit Hub",
        "name_for_model": "intelgit_hub",
        "description_for_human": "Search and reuse verified AI Knowledge Objects (ko://).",
        "description_for_model": (
            "IntelGit Hub stores cryptographically signed AI reasoning steps called "
            "Knowledge Objects (KOs). Use this plugin to: "
            "(1) search existing KOs by goal to avoid recomputing, "
            "(2) push new KOs after running an LLM, "
            "(3) retrieve the output of a KO by ID. "
            "Reusing a KO costs ~$0.000001 and ~8ms vs $0.01+ and 800ms for a fresh LLM call."
        ),
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": f"{base}/openapi.json",
        },
        "logo_url": f"{base}/logo.png",
        "contact_email": "hello@intelgit.ai",
        "legal_info_url": f"{base}/terms",
    }


@app.get("/openapi.json")
async def openapi():
    return app.openapi()


# ── Web dashboard (HTML) ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def landing_page():
    data = await stats()
    kos   = recent_kos(limit=6)
    recent_rows = "".join(
        f"<tr><td><code style='font-size:.75rem'>{r['id'][:28]}…</code></td>"
        f"<td>{r['goal'][:55]}</td><td>{r['reuse_count']}</td></tr>"
        for r in kos
    ) or "<tr><td colspan=3 style='text-align:center;color:#888'>Be the first to push a KO</td></tr>"

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>IntelGit – Verifiable AI Reasoning</title>
  <meta name="description" content="Stop paying twice for the same AI answer. IntelGit caches, signs, and shares verified AI reasoning — cheaper, faster, auditable.">
  <style>
    :root {{
      --bg:#0a0b0f; --surface:#13151f; --border:#1e2235;
      --accent:#7c6dff; --accent2:#00e5c0;
      --text:#e2e8f0; --muted:#8892b0;
    }}
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif;line-height:1.6}}
    a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}

    /* NAV */
    nav{{background:var(--surface);border-bottom:1px solid var(--border);
         padding:.9rem 2rem;display:flex;align-items:center;gap:1.5rem;position:sticky;top:0;z-index:10}}
    nav .logo{{font-weight:700;font-size:1.1rem;color:var(--text);letter-spacing:-.3px}}
    nav .logo span{{color:var(--accent)}}
    nav .spacer{{flex:1}}
    nav a{{color:var(--muted);font-size:.875rem}} nav a:hover{{color:var(--text)}}
    .nav-cta{{background:var(--accent);color:#fff!important;padding:.4rem 1rem;
              border-radius:8px;font-weight:600}} .nav-cta:hover{{opacity:.9;text-decoration:none!important}}

    /* HERO */
    .hero{{max-width:900px;margin:5rem auto 3rem;padding:0 2rem;text-align:center}}
    .hero h1{{font-size:clamp(2.2rem,5vw,3.6rem);font-weight:800;line-height:1.15;
              letter-spacing:-.03em;margin-bottom:1.25rem}}
    .hero h1 .hl{{background:linear-gradient(135deg,var(--accent),var(--accent2));
                  -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
    .hero p{{font-size:1.15rem;color:var(--muted);max-width:620px;margin:0 auto 2rem}}
    .hero-btns{{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap}}
    .btn-primary{{background:var(--accent);color:#fff;padding:.7rem 1.75rem;border-radius:10px;
                  font-weight:600;font-size:.95rem}} .btn-primary:hover{{opacity:.9;text-decoration:none}}
    .btn-secondary{{border:1px solid var(--border);color:var(--text);padding:.7rem 1.75rem;
                    border-radius:10px;font-weight:600;font-size:.95rem;background:var(--surface)}}
    .btn-secondary:hover{{border-color:var(--accent);text-decoration:none}}

    /* STATS BAR */
    .stats-bar{{display:flex;justify-content:center;gap:3rem;flex-wrap:wrap;
                margin:3rem auto;padding:2rem;max-width:860px;
                background:var(--surface);border:1px solid var(--border);border-radius:16px}}
    .stat{{text-align:center}}
    .stat .n{{font-size:2rem;font-weight:700;color:var(--accent2)}}
    .stat .l{{font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}

    /* INSTALL */
    .install{{max-width:640px;margin:0 auto 4rem;padding:0 2rem}}
    .install-box{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.25rem 1.5rem;
                  display:flex;align-items:center;gap:1rem}}
    .install-box code{{flex:1;font-size:.95rem;color:var(--accent2);font-family:'Fira Code',monospace}}
    .copy-btn{{background:var(--border);border:none;color:var(--muted);padding:.35rem .75rem;
               border-radius:6px;cursor:pointer;font-size:.8rem}}
    .copy-btn:hover{{color:var(--text)}}

    /* PILLARS */
    .pillars{{max-width:900px;margin:0 auto 5rem;padding:0 2rem}}
    .pillars h2{{text-align:center;font-size:1.6rem;font-weight:700;margin-bottom:2rem}}
    .pillars-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1.25rem}}
    .pillar{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.75rem}}
    .pillar .icon{{font-size:1.75rem;margin-bottom:.75rem}}
    .pillar h3{{font-size:1.05rem;font-weight:700;margin-bottom:.5rem}}
    .pillar p{{color:var(--muted);font-size:.875rem;line-height:1.6}}

    /* CODE */
    .code-section{{max-width:900px;margin:0 auto 5rem;padding:0 2rem}}
    .code-section h2{{text-align:center;font-size:1.6rem;font-weight:700;margin-bottom:2rem}}
    pre{{background:var(--surface);border:1px solid var(--border);border-radius:12px;
         padding:1.5rem;overflow-x:auto;font-size:.85rem;line-height:1.7;
         font-family:'Fira Code','Cascadia Code',monospace}}
    .cm{{color:#6272a4}} .ck{{color:var(--accent)}} .cs{{color:var(--accent2)}} .cn{{color:#f8f8f2}}

    /* RECENT KOs */
    .recent{{max-width:900px;margin:0 auto 5rem;padding:0 2rem}}
    .recent h2{{font-size:1.6rem;font-weight:700;margin-bottom:1.5rem;text-align:center}}
    table{{width:100%;border-collapse:collapse;font-size:.83rem}}
    th{{color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;
        padding:.6rem .75rem;border-bottom:1px solid var(--border);text-align:left}}
    td{{padding:.6rem .75rem;border-bottom:1px solid rgba(255,255,255,.04)}}
    tr:hover td{{background:rgba(124,109,255,.05)}}
    tr:last-child td{{border:none}}

    /* HOW */
    .how{{max-width:900px;margin:0 auto 5rem;padding:0 2rem;text-align:center}}
    .how h2{{font-size:1.6rem;font-weight:700;margin-bottom:2rem}}
    .steps{{display:flex;gap:0;flex-wrap:wrap;justify-content:center}}
    .step{{flex:1;min-width:160px;max-width:220px;padding:1.25rem}}
    .step .num{{width:36px;height:36px;border-radius:50%;background:var(--accent);color:#fff;
                font-weight:700;display:flex;align-items:center;justify-content:center;margin:0 auto .75rem}}
    .step h4{{font-size:.9rem;font-weight:600;margin-bottom:.4rem}}
    .step p{{color:var(--muted);font-size:.8rem}}
    .step-arrow{{display:flex;align-items:center;color:var(--border);font-size:1.5rem;padding-top:1.5rem}}

    /* CTA */
    .cta{{text-align:center;padding:4rem 2rem;background:var(--surface);
          border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin-bottom:3rem}}
    .cta h2{{font-size:1.8rem;font-weight:700;margin-bottom:.75rem}}
    .cta p{{color:var(--muted);margin-bottom:1.5rem}}

    /* FOOTER */
    footer{{text-align:center;padding:2rem;color:var(--muted);font-size:.8rem;border-top:1px solid var(--border)}}
    footer a{{color:var(--muted)}} footer a:hover{{color:var(--text)}}

    @media(max-width:600px){{
      .stats-bar{{gap:1.5rem}} .step-arrow{{display:none}}
    }}
  </style>
</head>
<body>

<nav>
  <span class="logo">⚡ Intel<span>Git</span></span>
  <span class="spacer"></span>
  <a href="/hub">Hub</a>
  <a href="/leaderboard">Leaderboard</a>
  <a href="/docs">API Docs</a>
  <a href="/v1/register" class="nav-cta">Get API Key</a>
</nav>

<!-- HERO -->
<section class="hero">
  <h1>Your AI agent is paying<br>for the same answer <span class="hl">twice.</span></h1>
  <p>IntelGit caches, cryptographically signs, and shares verified AI reasoning.
     Stop re-running LLMs. Start reusing Knowledge Objects.</p>
  <div class="hero-btns">
    <a href="#install" class="btn-primary">Install in 30 seconds</a>
    <a href="/docs" class="btn-secondary">Read the docs</a>
  </div>
</section>

<!-- LIVE STATS -->
<div class="stats-bar">
  <div class="stat"><div class="n">{data['total_kos']:,}</div><div class="l">Knowledge Objects</div></div>
  <div class="stat"><div class="n">{data['total_reuses']:,}</div><div class="l">Reuses</div></div>
  <div class="stat"><div class="n">{data['unique_agents']:,}</div><div class="l">AI Agents</div></div>
  <div class="stat"><div class="n">${data['total_cost_saved_usd']:.2f}</div><div class="l">Saved in LLM costs</div></div>
  <div class="stat"><div class="n">{int(data['total_latency_saved_ms']/1000):,}s</div><div class="l">Latency saved</div></div>
</div>

<!-- INSTALL -->
<div class="install" id="install">
  <div class="install-box">
    <code>pip install intelgit</code>
    <button class="copy-btn" onclick="navigator.clipboard.writeText('pip install intelgit');this.textContent='Copied!'">Copy</button>
  </div>
</div>

<!-- 3 PILLARS -->
<section class="pillars">
  <h2>Cheaper. Faster. Auditable.</h2>
  <div class="pillars-grid">
    <div class="pillar">
      <div class="icon">💸</div>
      <h3>Cheaper</h3>
      <p>Reusing a cached Knowledge Object costs <strong>$0.000001</strong>.
         Running the LLM again costs <strong>$0.003–0.03</strong>.
         At scale, this compounds fast.</p>
    </div>
    <div class="pillar">
      <div class="icon">⚡</div>
      <h3>Faster</h3>
      <p>Cache hit returns in <strong>~8ms</strong>. A fresh GPT-4o call
         takes <strong>800ms–3s</strong>. Your agents stop waiting for answers
         they've already paid for.</p>
    </div>
    <div class="pillar">
      <div class="icon">🔏</div>
      <h3>Auditable</h3>
      <p>Every Knowledge Object is <strong>Ed25519-signed</strong> with a DID key.
         You can prove what your AI said, which model ran it, and that
         the output was never changed. Built for compliance.</p>
    </div>
  </div>
</section>

<!-- CODE EXAMPLE -->
<section class="code-section">
  <h2>Two lines to never pay twice</h2>
  <pre><span class="cm"># Wrap any LangChain LLM — no other changes needed</span>
<span class="ck">from</span> <span class="cn">intelgit</span> <span class="ck">import</span> <span class="cn">KOAgent</span>
<span class="ck">from</span> <span class="cn">langchain_openai</span> <span class="ck">import</span> <span class="cn">ChatOpenAI</span>

<span class="cn">agent</span> <span class="ck">=</span> <span class="cn">KOAgent</span>(<span class="cn">ChatOpenAI</span>(<span class="cs">model</span><span class="ck">=</span><span class="cs">"gpt-4o-mini"</span>))

<span class="cm"># First call → hits GPT, commits a signed Knowledge Object</span>
<span class="cn">result</span> <span class="ck">=</span> <span class="cn">agent</span>.<span class="cn">invoke</span>(<span class="cs">"Summarise EU AI Act compliance requirements"</span>)

<span class="cm"># Second call (same or similar goal) → 8ms cache hit, $0.000001</span>
<span class="cn">result2</span> <span class="ck">=</span> <span class="cn">agent</span>.<span class="cn">invoke</span>(<span class="cs">"Summarise EU AI Act compliance requirements"</span>)

<span class="cn">agent</span>.<span class="cn">print_stats</span>()
<span class="cm"># Cache hits: 1/2 | Saved: $0.0034 | Saved: 1847ms</span></pre>
</section>

<!-- HOW IT WORKS -->
<section class="how">
  <h2>How it works</h2>
  <div class="steps">
    <div class="step">
      <div class="num">1</div>
      <h4>Run your LLM</h4>
      <p>IntelGit wraps your existing call — nothing changes in your code</p>
    </div>
    <div class="step-arrow">→</div>
    <div class="step">
      <div class="num">2</div>
      <h4>Sign & cache</h4>
      <p>Output is hashed, signed with your DID key, saved as a Knowledge Object</p>
    </div>
    <div class="step-arrow">→</div>
    <div class="step">
      <div class="num">3</div>
      <h4>Reuse or share</h4>
      <p>Next identical call hits the cache. Push to the registry so others benefit too</p>
    </div>
    <div class="step-arrow">→</div>
    <div class="step">
      <div class="num">4</div>
      <h4>Earn micro-royalties</h4>
      <p>Every time someone reuses your KO, you earn $0.000001 automatically</p>
    </div>
  </div>
</section>

<!-- RECENT KOs -->
<section class="recent">
  <h2>Recently published Knowledge Objects</h2>
  <table>
    <thead><tr><th>ID</th><th>Goal</th><th>Reuses</th></tr></thead>
    <tbody>{recent_rows}</tbody>
  </table>
  <p style="text-align:center;margin-top:1.25rem">
    <a href="/hub">Browse all Knowledge Objects →</a>
  </p>
</section>

<!-- CTA -->
<div class="cta">
  <h2>Start for free. No credit card.</h2>
  <p>Install locally in seconds. Push to the registry when you're ready.</p>
  <div style="display:flex;gap:1rem;justify-content:center;flex-wrap:wrap">
    <a href="#install" class="btn-primary">pip install intelgit</a>
    <a href="/v1/register" class="btn-secondary">Get API key</a>
  </div>
</div>

<footer>
  <p>
    <a href="/hub">Hub</a> &nbsp;·&nbsp;
    <a href="/leaderboard">Leaderboard</a> &nbsp;·&nbsp;
    <a href="/packages">Packages</a> &nbsp;·&nbsp;
    <a href="/docs">API Docs</a> &nbsp;·&nbsp;
    <a href="/v1/stats">Stats JSON</a> &nbsp;·&nbsp;
    <a href="/.well-known/ai-plugin.json">AI Plugin</a>
  </p>
  <p style="margin-top:.75rem">IntelGit – Git for Intelligence &nbsp;·&nbsp; Free & open source</p>
</footer>

</body>
</html>""")


@app.get("/hub", response_class=HTMLResponse)
async def dashboard_home():
    kos = recent_kos(limit=20)
    rows = "".join(
        f"<tr><td><a href='/ko/{r['id']}'>{r['id'][:28]}…</a></td>"
        f"<td>{r['goal'][:65]}</td><td>{r['reuse_count']}</td>"
        f"<td>{r['confidence']:.2f}</td></tr>"
        for r in kos
    )
    return HTMLResponse(_page(
        "IntelGit Hub – Recent KOs",
        f"""<h2>Recent Knowledge Objects</h2>
        <table>
          <thead><tr><th>ID</th><th>Goal</th><th>Reuses</th><th>Confidence</th></tr></thead>
          <tbody>{rows or '<tr><td colspan=4>No KOs yet.</td></tr>'}</tbody>
        </table>
        <p style="margin-top:1rem">
          <a href='/leaderboard'>Leaderboard</a> &nbsp;|&nbsp;
          <a href='/packages'>Packages</a>
        </p>""",
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


@app.get("/stats", response_class=HTMLResponse)
async def dashboard_stats():
    s = (await stats()).body if hasattr(await stats(), "body") else await stats()
    # stats() returns a dict directly
    data = await stats()
    saved_usd = data["total_cost_saved_usd"]
    saved_s = data["total_latency_saved_ms"] / 1000
    top = data.get("top_ko") or {}
    return HTMLResponse(_page(
        "IntelGit Hub – Stats",
        f"""
        <h2>Registry Stats</h2>
        <table>
          <tr><th>Total KOs</th><td><strong>{data['total_kos']}</strong></td></tr>
          <tr><th>Total Reuses</th><td><strong>{data['total_reuses']}</strong></td></tr>
          <tr><th>Unique Agents</th><td><strong>{data['unique_agents']}</strong></td></tr>
          <tr><th>Cost Saved</th><td><strong>${saved_usd:.4f}</strong></td></tr>
          <tr><th>Latency Saved</th><td><strong>{saved_s:.1f}s</strong></td></tr>
          <tr><th>Top KO</th><td>{top.get('goal','—')[:60]} ({top.get('reuse_count',0)} reuses)</td></tr>
        </table>
        <p style="margin-top:1rem"><a href='/'>← Back</a> | <a href='/v1/stats'>JSON</a></p>
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
  <header><h1><a href="/" style="text-decoration:none">⚡ IntelGit Hub</a></h1>
  <nav><a href="/hub">Browse</a> | <a href="/leaderboard">Leaderboard</a> | <a href="/docs">API</a></nav></header>
  <main>{body}</main>
  <footer><small>IntelGit – Git for Intelligence</small></footer>
</body>
</html>"""


def start():
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    start()

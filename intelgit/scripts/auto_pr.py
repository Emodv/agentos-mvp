#!/usr/bin/env python3
"""
auto_pr.py – Automatically create IntelGit integration PRs for repos that
showed interest during outreach (status = 'responded' in contacts.db).

Workflow:
  1. Load responded repos from contacts.db
  2. Fork the repo (or use existing fork)
  3. Create a new branch: add-intelgit-example
  4. Add intelgit_example.py showing ko.reuse() usage
  5. Open a PR with a friendly pitch

Requires: GITHUB_TOKEN env var with repo + workflow scopes.
"""

import os
import sys
import json
import time
import sqlite3
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "contacts.db"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API   = "https://api.github.com"

EXAMPLE_FILE = "intelgit_example.py"
EXAMPLE_CODE = '''\
"""IntelGit integration example – auto-generated."""
# pip install intelgit
from intelgit import KOAgent
from langchain_openai import ChatOpenAI

# Wrap any LangChain LLM with transparent KO caching
llm   = ChatOpenAI(model="gpt-4o-mini")
agent = KOAgent(llm, similarity_threshold=0.85)

# First call: hits the LLM and commits a signed KO
result = agent.invoke("Summarise the README of this repo")
print(result)

# Second call: served from cache in ~8 ms instead of ~2 s
result2 = agent.invoke("Summarise the README of this repo")
print(result2)

agent.print_stats()
# => Cache hits: 1/2 | Saved: $0.0034 | Saved: 1847ms
'''

PR_TITLE = "feat: add IntelGit KO caching example"
PR_BODY  = """\
Hi! 👋

I noticed your project uses LLMs and wanted to share something that might \
save you money and latency: **IntelGit** – Git for Intelligence.

It cryptographically signs and caches AI reasoning outputs so you can \
replay them at ~8ms instead of calling the LLM again.

This PR adds a minimal example (`intelgit_example.py`) showing how to \
wrap your existing LangChain LLM with a one-liner.

**What it does:**
- First call → hits LLM, commits a signed Knowledge Object (KO)
- Subsequent identical/similar calls → served from cache in ~8ms
- Each reuse pays a micro-royalty ($0.000001) to the original prompter

**Zero lock-in** – it wraps any LangChain LLM and stores KOs locally by \
default (no cloud dependency unless you want to share them).

```bash
pip install intelgit
ko commit --goal "your task" --model gpt-4o-mini
```

Happy to answer questions or adjust the example for your use case!

— via [IntelGit](https://github.com/emodv/l2agent) (automated PR)
"""

BRANCH_NAME = "add-intelgit-example"


# ─── GitHub helpers ────────────────────────────────────────────────────────────

def _gh(method: str, path: str, body: dict | None = None, *, token: str = GITHUB_TOKEN):
    url = f"{GITHUB_API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "IntelGit-AutoPR/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read()) if resp.status not in (204,) else {}
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode(errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} → HTTP {e.code}: {body_txt}") from e


def get_authenticated_user() -> str:
    return _gh("GET", "/user")["login"]


def get_default_branch(owner: str, repo: str) -> str:
    info = _gh("GET", f"/repos/{owner}/{repo}")
    return info.get("default_branch", "main")


def get_branch_sha(owner: str, repo: str, branch: str) -> str:
    ref = _gh("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
    return ref["object"]["sha"]


def fork_repo(owner: str, repo: str) -> dict:
    return _gh("POST", f"/repos/{owner}/{repo}/forks", {})


def branch_exists(owner: str, repo: str, branch: str) -> bool:
    try:
        _gh("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
        return True
    except RuntimeError:
        return False


def create_branch(owner: str, repo: str, branch: str, sha: str):
    _gh("POST", f"/repos/{owner}/{repo}/git/refs", {
        "ref": f"refs/heads/{branch}",
        "sha": sha,
    })


def file_exists(owner: str, repo: str, path: str, branch: str) -> bool:
    try:
        _gh("GET", f"/repos/{owner}/{repo}/contents/{path}?ref={branch}")
        return True
    except RuntimeError:
        return False


def create_file(owner: str, repo: str, path: str, content: str, branch: str, message: str):
    import base64
    _gh("PUT", f"/repos/{owner}/{repo}/contents/{path}", {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    })


def create_pull_request(owner: str, repo: str, head_owner: str, branch: str,
                        base_branch: str, title: str, body: str) -> str:
    head = f"{head_owner}:{branch}" if head_owner != owner else branch
    pr = _gh("POST", f"/repos/{owner}/{repo}/pulls", {
        "title": title,
        "body": body,
        "head": head,
        "base": base_branch,
        "maintainer_can_modify": True,
    })
    return pr.get("html_url", "")


def pr_exists(owner: str, repo: str, head_owner: str, branch: str) -> bool:
    head = f"{head_owner}:{branch}"
    prs = _gh("GET", f"/repos/{owner}/{repo}/pulls?state=open&head={head}")
    return len(prs) > 0


# ─── DB helpers ───────────────────────────────────────────────────────────────

def load_responded_repos() -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, platform, username, repo_url, status
        FROM prospects
        WHERE status IN ('responded', 'interested')
          AND platform = 'github'
          AND repo_url IS NOT NULL
          AND repo_url != ''
        ORDER BY id
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def mark_pr_created(prospect_id: int, pr_url: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO outreach_log (prospect_id, platform, action, sent_at) VALUES (?,?,?,?)",
        (prospect_id, "github", f"pr_created:{pr_url}", datetime.now(timezone.utc).isoformat()),
    )
    conn.execute("UPDATE prospects SET status = 'pr_opened' WHERE id = ?", (prospect_id,))
    conn.commit()
    conn.close()


# ─── Core logic ───────────────────────────────────────────────────────────────

def _parse_repo_url(url: str) -> tuple[str, str] | None:
    # https://github.com/owner/repo  or  owner/repo
    url = url.strip().rstrip("/")
    if "github.com" in url:
        parts = url.split("github.com/")[-1].split("/")
    else:
        parts = url.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


def process_repo(prospect: dict, me: str, *, dry_run: bool, interactive: bool) -> bool:
    """Create an IntelGit example PR for a single repo. Returns True on success."""
    parsed = _parse_repo_url(prospect.get("repo_url", ""))
    if not parsed:
        print(f"  [SKIP] Cannot parse repo URL: {prospect['repo_url']}")
        return False

    owner, repo = parsed
    print(f"\n→ {owner}/{repo}  (prospect #{prospect['id']})")

    if interactive:
        ans = input(f"  Create PR for {owner}/{repo}? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("  Skipped.")
            return False

    if dry_run:
        print(f"  [DRY-RUN] Would fork {owner}/{repo}, create branch '{BRANCH_NAME}', open PR")
        return True

    try:
        default_branch = get_default_branch(owner, repo)

        # Fork (or reuse existing fork)
        print(f"  Forking {owner}/{repo}…")
        fork_repo(owner, repo)
        time.sleep(3)  # GitHub needs a moment to create the fork

        fork_owner = me

        # Get the SHA from the fork (it mirrors the upstream default branch)
        try:
            sha = get_branch_sha(fork_owner, repo, default_branch)
        except RuntimeError:
            sha = get_branch_sha(owner, repo, default_branch)

        # Create feature branch
        if branch_exists(fork_owner, repo, BRANCH_NAME):
            print(f"  Branch '{BRANCH_NAME}' already exists on fork")
        else:
            print(f"  Creating branch '{BRANCH_NAME}'…")
            create_branch(fork_owner, repo, BRANCH_NAME, sha)

        # Add example file
        if file_exists(fork_owner, repo, EXAMPLE_FILE, BRANCH_NAME):
            print(f"  {EXAMPLE_FILE} already exists on branch")
        else:
            print(f"  Adding {EXAMPLE_FILE}…")
            create_file(
                fork_owner, repo, EXAMPLE_FILE, EXAMPLE_CODE,
                BRANCH_NAME, "feat: add IntelGit KO caching example",
            )

        # Open PR
        if pr_exists(owner, repo, fork_owner, BRANCH_NAME):
            print(f"  PR already open")
            return True

        print(f"  Opening PR…")
        pr_url = create_pull_request(
            owner, repo, fork_owner, BRANCH_NAME,
            default_branch, PR_TITLE, PR_BODY,
        )
        print(f"  ✓ PR created: {pr_url}")
        mark_pr_created(prospect["id"], pr_url)
        return True

    except RuntimeError as e:
        print(f"  [ERROR] {e}")
        return False


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Create IntelGit example PRs for repos that responded to outreach"
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Preview only, don't create PRs (default: on)")
    parser.add_argument("--live", action="store_true",
                        help="Actually create PRs (disables dry-run)")
    parser.add_argument("--interactive", action="store_true",
                        help="Approve each PR interactively")
    parser.add_argument("--max", type=int, default=5,
                        help="Max PRs to create per run (default: 5)")
    parser.add_argument("--token", default=GITHUB_TOKEN,
                        help="GitHub token (default: $GITHUB_TOKEN)")
    args = parser.parse_args()

    dry_run     = not args.live
    interactive = args.interactive
    token       = args.token

    if not token:
        print("ERROR: GITHUB_TOKEN is not set. Export it or pass --token.", file=sys.stderr)
        sys.exit(1)

    global GITHUB_TOKEN
    GITHUB_TOKEN = token

    print("IntelGit Auto-PR")
    print("=" * 50)
    if dry_run:
        print("Mode: DRY-RUN (pass --live to actually create PRs)")
    else:
        print("Mode: LIVE")

    me = get_authenticated_user()
    print(f"Authenticated as: {me}")

    repos = load_responded_repos()
    if not repos:
        print("\nNo responded repos found in contacts.db.")
        print("Run `ko ambassador` to build your pipeline first.")
        sys.exit(0)

    print(f"\nFound {len(repos)} repo(s) with status 'responded' or 'interested'")

    created = 0
    for prospect in repos:
        if created >= args.max:
            print(f"\nReached limit of {args.max} PRs. Run again to continue.")
            break
        ok = process_repo(prospect, me, dry_run=dry_run, interactive=interactive)
        if ok:
            created += 1
        if not dry_run:
            time.sleep(2)  # be polite to the GitHub API

    print(f"\n{'[DRY-RUN] Would have created' if dry_run else 'Created'} {created} PR(s)")


if __name__ == "__main__":
    main()

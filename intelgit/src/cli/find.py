import click

from ..core import config
from ..core.store import KOLocalStore
from ..core.registry_client import RegistryClient

REUSE_COST_USD = 0.000001
REUSE_LATENCY_MS = 8


@click.command()
@click.argument("query")
@click.option("--top-k", default=5, show_default=True)
@click.option("--threshold", default=0.3, show_default=True,
              help="Minimum similarity score [0-1]")
@click.option("--remote/--no-remote", default=True,
              help="Also search global registry if local results < top-k")
@click.option("--json-out", is_flag=True, default=False)
def find(query: str, top_k: int, threshold: float, remote: bool, json_out: bool):
    """
    Find knowledge objects similar to QUERY.

    Searches local store first, then falls back to the global registry
    for any remaining slots (transparent, requires ko login).
    """
    store = KOLocalStore()
    local_results = store.find_similar(query, top_k=top_k, threshold=threshold)

    # Remote fallback
    remote_results = []
    if remote and len(local_results) < top_k:
        cfg = config.load()
        url = cfg.get("registry_url")
        if url:
            client = RegistryClient(url)
            remote_hits = client.search(query, top_k=top_k - len(local_results))
            local_ids = {r.ko.id for r in local_results}
            for hit in remote_hits:
                if hit.get("id") not in local_ids:
                    remote_results.append(hit)

    if not local_results and not remote_results:
        click.echo("No matching knowledge objects found above threshold.")
        return

    if json_out:
        import json
        out = (
            [{"source": "local", "match_score": r.score, "existing_ko": r.ko.id,
              "goal": r.ko.goal, "reuse_cost_usd": REUSE_COST_USD,
              "reuse_latency_ms": REUSE_LATENCY_MS, "confidence": r.ko.confidence}
             for r in local_results]
            +
            [{"source": "registry", "match_score": None, "existing_ko": r.get("id"),
              "goal": r.get("goal"), "reuse_count": r.get("reuse_count", 0)}
             for r in remote_results]
        )
        click.echo(json.dumps(out, indent=2))
        return

    total = len(local_results) + len(remote_results)
    click.echo(f"Found {total} result(s) for: {query!r}\n")

    for i, result in enumerate(local_results, 1):
        ko = result.ko
        has_output = store.get_output(ko.id) is not None
        click.echo(f"  {i}. [local] score={result.score:.2f}  {'[output cached]' if has_output else '[no local output]'}")
        click.echo(f"     id:    {ko.id}")
        click.echo(f"     goal:  {ko.goal[:70]}")
        click.echo(f"     reuse: ${REUSE_COST_USD:.6f}  latency ~{REUSE_LATENCY_MS}ms")
        click.echo()

    for j, r in enumerate(remote_results, len(local_results) + 1):
        click.echo(f"  {j}. [registry]  reuses={r.get('reuse_count', 0)}")
        click.echo(f"     id:    {r.get('id')}")
        click.echo(f"     goal:  {r.get('goal', '')[:70]}")
        click.echo(f"     tip:   run `ko install {r.get('id')}` to cache locally")
        click.echo()

    click.echo("Run `ko reuse <id>` (local) or `ko install <id>` (registry) to use a result.")

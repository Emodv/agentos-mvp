import click

from ..core.store import KOLocalStore

REUSE_COST_USD = 0.000001
REUSE_LATENCY_MS = 8


@click.command()
@click.argument("query")
@click.option("--top-k", default=5, show_default=True)
@click.option("--threshold", default=0.3, show_default=True,
              help="Minimum similarity score [0-1]")
@click.option("--semantic", is_flag=True, default=False,
              help="Use sentence-embeddings (requires sentence-transformers)")
@click.option("--json-out", is_flag=True, default=False)
def find(query: str, top_k: int, threshold: float, semantic: bool, json_out: bool):
    """Find knowledge objects similar to QUERY."""
    store = KOLocalStore()
    results = store.find_similar(query, top_k=top_k, threshold=threshold)

    if not results:
        click.echo("No matching knowledge objects found above threshold.")
        return

    if json_out:
        import json
        out = [
            {
                "match_score": r.score,
                "existing_ko": r.ko.id,
                "goal": r.ko.goal,
                "reuse_cost_usd": REUSE_COST_USD,
                "reuse_latency_ms": REUSE_LATENCY_MS,
                "confidence": r.ko.confidence,
            }
            for r in results
        ]
        click.echo(json.dumps(out, indent=2))
        return

    click.echo(f"Found {len(results)} result(s) for: {query!r}\n")
    for i, result in enumerate(results, 1):
        ko = result.ko
        has_output = store.get_output(ko.id) is not None
        click.echo(f"  {i}. score={result.score:.2f}  {'[output cached]' if has_output else '[no local output]'}")
        click.echo(f"     id:      {ko.id}")
        click.echo(f"     goal:    {ko.goal}")
        click.echo(f"     model:   {ko.proof.model}  conf={ko.confidence}")
        click.echo(f"     reuse:   ${REUSE_COST_USD:.6f}  latency ~{REUSE_LATENCY_MS}ms")
        if i < len(results):
            click.echo()

    click.echo(f"\nRun `ko reuse <id>` to reuse a KO without re-running the LLM.")

import json

import click

from ..core.config import get as cfg_get
from ..core.registry_client import RegistryClient
from ..core.store import KOLocalStore
from ..core.ko import KnowledgeObject, Proof
from datetime import datetime, timezone


@click.command()
@click.argument("query")
@click.option("--registry", default=None, help="Override registry URL")
@click.option("--top-k", default=5, show_default=True)
@click.option("--yes", "-y", is_flag=True, default=False, help="Auto-accept first result")
def install(query: str, registry: str, top_k: int, yes: bool):
    """
    Search the global registry for a KO and install it locally.

    QUERY can be a goal description (fuzzy) or an exact ko:// ID.
    """
    url = registry or cfg_get("registry_url") or "https://l2agent-production.up.railway.app"
    client = RegistryClient(url)
    store = KOLocalStore()

    # Direct ID lookup
    if query.startswith("ko://"):
        _install_by_id(query, client, store, url)
        return

    click.echo(f"Searching {url} for: {query!r} …")
    results = client.search(query, top_k=top_k)
    if not results:
        click.echo("No results found in registry.")
        raise SystemExit(1)

    click.echo(f"\nFound {len(results)} result(s):\n")
    for i, r in enumerate(results, 1):
        click.echo(
            f"  {i}. [{r.get('reuse_count', 0)} reuses]  {r['id']}\n"
            f"     {r['goal'][:80]}"
        )

    choice = 1
    if not yes:
        choice = click.prompt("\nInstall which?", type=int, default=1)
    if choice < 1 or choice > len(results):
        click.echo("Invalid choice.")
        raise SystemExit(1)

    ko_id = results[choice - 1]["id"]
    _install_by_id(ko_id, client, store, url)


def _install_by_id(ko_id: str, client: RegistryClient, store: KOLocalStore, url: str):
    click.echo(f"Fetching {ko_id} from {url} …")
    ko_data = client.get_ko(ko_id)
    if not ko_data:
        click.echo(f"KO not found on registry: {ko_id}", err=True)
        raise SystemExit(1)

    # Reconstruct KO object
    proof_data = ko_data.get("proof", {})
    if isinstance(proof_data, str):
        proof_data = json.loads(proof_data)
    ko = KnowledgeObject(
        id=ko_data["id"],
        goal=ko_data["goal"],
        inputs=ko_data.get("inputs") or {},
        output_hash=ko_data.get("output_hash", ""),
        proof=Proof(**proof_data),
        dependencies=ko_data.get("dependencies") or [],
        confidence=ko_data.get("confidence", 0.5),
        cost_usd=ko_data.get("cost_usd", 0.0),
        latency_ms=ko_data.get("latency_ms", 0),
        license=ko_data.get("license", "reuse-with-attribution"),
        created_at=datetime.fromisoformat(ko_data.get("created_at") or datetime.now(timezone.utc).isoformat()),
    )

    # Fetch output
    output_bytes = client.get_output(ko_id)

    store.put(ko, output_bytes)
    client.record_reuse(ko_id)

    click.echo(f"Installed: {ko.id}")
    click.echo(f"Goal:      {ko.goal}")
    if output_bytes:
        click.echo(f"Output:    {output_bytes.decode(errors='replace')[:200]}")
    click.echo(f"\nRun `ko reuse {ko.id}` to use it.")

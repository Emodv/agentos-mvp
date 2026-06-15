import json

import click

from ..core.store import KOLocalStore


@click.command()
@click.argument("ko_id")
@click.option("--json-out", is_flag=True, default=False, help="Output full KO as JSON")
def checkout(ko_id: str, json_out: bool):
    """Retrieve a knowledge object's metadata by ID."""
    store = KOLocalStore()
    ko = store.get(ko_id)
    if not ko:
        click.echo(f"KO not found: {ko_id}", err=True)
        raise SystemExit(1)

    if json_out:
        click.echo(json.dumps(ko.to_dict(), indent=2, default=str))
        return

    click.echo(f"ID:          {ko.id}")
    click.echo(f"Goal:        {ko.goal}")
    click.echo(f"Model:       {ko.proof.model}")
    click.echo(f"Confidence:  {ko.confidence}")
    click.echo(f"Cost:        ${ko.cost_usd:.6f}")
    click.echo(f"Latency:     {ko.latency_ms} ms")
    click.echo(f"License:     {ko.license}")
    click.echo(f"Created:     {ko.created_at.isoformat()}")
    click.echo(f"Output hash: {ko.output_hash}")
    click.echo(f"Signer DID:  {ko.proof.signer_did}")
    if ko.dependencies:
        click.echo(f"Deps:        {', '.join(ko.dependencies)}")

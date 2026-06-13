import click

from ..core.store import KOLocalStore


@click.command()
@click.argument("ko_id")
def push(ko_id: str):
    """Publish a knowledge object to IPFS (requires IPFS daemon)."""
    store = KOLocalStore()
    ko = store.get(ko_id)
    if not ko:
        click.echo(f"KO not found: {ko_id}", err=True)
        raise SystemExit(1)

    ipfs = store._get_ipfs()
    if not ipfs:
        click.echo("IPFS daemon not available. Start with: ipfs daemon", err=True)
        raise SystemExit(1)

    import json
    payload = json.dumps(ko.to_dict(), indent=2, default=str).encode()
    cid = ipfs.add_bytes(payload)
    click.echo(f"Published to IPFS: {cid}")
    click.echo(f"KO ID: {ko_id}")

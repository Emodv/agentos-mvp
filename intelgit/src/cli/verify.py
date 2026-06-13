import click

from ..core.crypto import verify_signature
from ..core.store import KOLocalStore


@click.command()
@click.argument("ko_id")
def verify(ko_id: str):
    """Cryptographically verify a knowledge object's integrity and signature."""
    store = KOLocalStore()
    ko = store.get(ko_id)
    if not ko:
        click.echo(f"KO not found: {ko_id}", err=True)
        raise SystemExit(1)

    # 1. ID integrity check
    recomputed = ko.compute_id()
    if recomputed != ko_id:
        click.echo(f"FAIL  ID mismatch\n  stored:     {ko_id}\n  recomputed: {recomputed}")
        raise SystemExit(2)
    click.echo(f"PASS  ID integrity")

    # 2. Signature check
    ko_dict = ko.to_dict()
    if verify_signature(ko_dict, ko.proof.signature, ko.proof.signer_did):
        click.echo(f"PASS  Signature ({ko.proof.signer_did[:30]}…)")
    else:
        click.echo(f"FAIL  Invalid signature")
        raise SystemExit(2)

    click.echo(f"\nKO {ko_id} is VALID.")

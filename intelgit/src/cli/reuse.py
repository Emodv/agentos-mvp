import click

from ..core.crypto import verify_signature
from ..core.store import KOLocalStore

REUSE_COST_USD = 0.000001
REUSE_LATENCY_MS = 8


@click.command()
@click.argument("ko_id")
@click.option("--no-verify", is_flag=True, default=False,
              help="Skip cryptographic verification (faster, less safe)")
@click.option("--quiet", is_flag=True, default=False,
              help="Print only the output text")
def reuse(ko_id: str, no_verify: bool, quiet: bool):
    """
    Reuse a knowledge object's cached output without calling the LLM.

    Verifies the KO's cryptographic signature before returning the output,
    and reports the simulated micropayment to the original creator.
    """
    store = KOLocalStore()
    ko = store.get(ko_id)
    if not ko:
        click.echo(f"KO not found: {ko_id}", err=True)
        raise SystemExit(1)

    if not no_verify:
        ko_dict = ko.to_dict()
        if ko.compute_id() != ko_id:
            click.echo("FAIL  ID integrity check — KO may be corrupted.", err=True)
            raise SystemExit(2)
        if not verify_signature(ko_dict, ko.proof.signature, ko.proof.signer_did):
            click.echo("FAIL  Invalid signature — refusing to reuse.", err=True)
            raise SystemExit(2)

    output = store.get_output(ko_id)
    if output is None:
        click.echo(
            f"No local output cached for {ko_id}.\n"
            "Re-run `ko commit` with the same goal to populate the cache.",
            err=True,
        )
        raise SystemExit(1)

    if quiet:
        click.echo(output)
        return

    click.echo(f"Output: {output}")
    if not no_verify:
        click.echo(f"Verified signature ({ko.proof.signer_did[:32]}…)")
    click.echo(f"Paid ${REUSE_COST_USD:.6f} to creator  |  latency ~{REUSE_LATENCY_MS}ms")

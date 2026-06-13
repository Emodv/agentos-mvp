import click

from ..core import config
from ..core.crypto import verify_signature
from ..core.registry_client import RegistryClient
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

    Checks local cache first, then transparently fetches from the global
    registry and installs locally if not found.
    """
    store = KOLocalStore()
    ko = store.get(ko_id)
    output = store.get_output(ko_id) if ko else None

    # Registry fallback
    if ko is None or output is None:
        cfg = config.load()
        url = cfg.get("registry_url")
        if url:
            if not quiet:
                click.echo(f"Not in local cache – fetching from registry …")
            client = RegistryClient(url)

            if ko is None:
                ko_data = client.get_ko(ko_id)
                if ko_data:
                    _store_remote_ko(ko_data, store)
                    ko = store.get(ko_id)

            if output is None and ko:
                raw = client.get_output(ko_id)
                if raw:
                    store._write_output(ko_id, raw)
                    output = raw.decode(errors="replace")
                    client.record_reuse(ko_id)

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

    if output is None:
        click.echo(
            f"No output cached for {ko_id}.\n"
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
    saved_usd = ko.cost_usd - REUSE_COST_USD
    saved_ms = ko.latency_ms - REUSE_LATENCY_MS
    click.echo(
        f"Paid ${REUSE_COST_USD:.6f} to creator  |  "
        f"latency ~{REUSE_LATENCY_MS}ms  |  "
        f"saved ${saved_usd:.4f} and {saved_ms}ms vs re-running"
    )

    # Viral sharing prompt
    if saved_usd > 0.001:
        share = click.confirm(
            f"\nShare this win? (tweet: saved ${saved_usd:.4f} with IntelGit)",
            default=False,
        )
        if share:
            tweet = (
                f"My AI agent just saved ${saved_usd:.4f} and {saved_ms}ms "
                f"reusing a verified knowledge object with @IntelGit. "
                f"pip install intelgit #AIagents #LLM"
            )
            click.echo(f"\nTweet:\n{tweet}")
            click.echo(f"\nShare at: https://twitter.com/intent/tweet?text={_url_encode(tweet)}")


def _url_encode(text: str) -> str:
    from urllib.parse import quote
    return quote(text, safe="")


def _store_remote_ko(ko_data: dict, store: KOLocalStore):
    """Reconstruct and locally store a KO fetched from registry."""
    import json
    from datetime import datetime, timezone
    from ..core.ko import KnowledgeObject, Proof
    proof_data = ko_data.get("proof") or {}
    if isinstance(proof_data, str):
        proof_data = json.loads(proof_data)
    try:
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
            created_at=datetime.fromisoformat(
                ko_data.get("created_at") or datetime.now(timezone.utc).isoformat()
            ),
        )
        store.put(ko)
    except Exception:
        pass

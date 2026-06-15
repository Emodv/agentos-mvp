import click

from ..core.config import get as cfg_get
from ..core.registry_client import RegistryClient
from ..core.store import KOLocalStore


@click.command()
@click.argument("ko_id", required=False)
@click.option("--all", "push_all", is_flag=True, default=False, help="Push all local KOs")
@click.option("--registry", default=None, help="Override registry URL")
def push(ko_id: str, push_all: bool, registry: str):
    """Publish one or all local KOs to the IntelGit Hub registry."""
    url = registry or cfg_get("registry_url") or "https://hub.intelgit.ai"
    client = RegistryClient(url)
    store = KOLocalStore()

    kos_to_push = []
    if push_all:
        kos_to_push = store.list_all(limit=9999)
    elif ko_id:
        ko = store.get(ko_id)
        if not ko:
            click.echo(f"KO not found: {ko_id}", err=True)
            raise SystemExit(1)
        kos_to_push = [ko]
    else:
        click.echo("Specify a KO ID or --all.", err=True)
        raise SystemExit(1)

    ok = fail = 0
    for ko in kos_to_push:
        output_bytes = None
        raw = store.get_output(ko.id)
        if raw:
            output_bytes = raw.encode()

        ko_dict = ko.to_dict()
        result = client.push(ko_dict, output_bytes)
        if result and result.get("verified"):
            click.echo(f"  pushed  {ko.id}")
            ok += 1
        else:
            msg = (result or {}).get("detail", "network error")
            click.echo(f"  failed  {ko.id}  ({msg})")
            fail += 1

    click.echo(f"\nDone: {ok} pushed, {fail} failed.  Registry: {url}")

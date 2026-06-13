import click

from .cli.commit import commit
from .cli.checkout import checkout
from .cli.verify import verify
from .cli.push import push
from .cli.install import install
from .cli.find import find
from .cli.reuse import reuse
from .cli.config_cmd import config_cmd
from .cli.login import login
from .cli.status import status, whoami, balance
from .cli.ambassador import ambassador
from .core.store import KOLocalStore


@click.group()
def cli():
    """ko – Git for Intelligence. Version-control your reasoning."""


@cli.command(name="log")
@click.option("--limit", default=10, show_default=True)
def log_cmd(limit: int):
    """List recently committed knowledge objects."""
    store = KOLocalStore()
    kos = store.list_all(limit=limit)
    if not kos:
        click.echo("No knowledge objects committed yet.")
        return
    for ko in kos:
        click.echo(f"{ko.id}  {ko.created_at.strftime('%Y-%m-%d %H:%M')}  {ko.goal[:60]}")


@cli.command(name="search")
@click.argument("query")
@click.option("--top-k", default=5, show_default=True)
@click.option("--registry", is_flag=True, default=False,
              help="Also search the global registry")
def search_cmd(query: str, top_k: int, registry: bool):
    """Search knowledge objects by goal text."""
    store = KOLocalStore()
    results = store.search_by_goal(query, top_k=top_k)
    if results:
        click.echo("Local results:")
        for ko in results:
            click.echo(f"  {ko.id}  {ko.goal[:70]}")
    else:
        click.echo("No local results.")

    if registry:
        from .core.config import get as cfg_get
        from .core.registry_client import RegistryClient
        url = cfg_get("registry_url") or "https://hub.intelgit.ai"
        client = RegistryClient(url)
        remote = client.search(query, top_k=top_k)
        click.echo(f"\nRegistry results ({url}):")
        if remote:
            for r in remote:
                click.echo(f"  [{r.get('reuse_count', 0)}x]  {r['id']}  {r['goal'][:60]}")
        else:
            click.echo("  (none or registry unreachable)")


cli.add_command(commit)
cli.add_command(checkout)
cli.add_command(verify)
cli.add_command(push)
cli.add_command(install)
cli.add_command(find)
cli.add_command(reuse)
cli.add_command(config_cmd)
cli.add_command(login)
cli.add_command(status)
cli.add_command(whoami)
cli.add_command(balance)
cli.add_command(ambassador)


if __name__ == "__main__":
    cli()

import click

from .cli.commit import commit
from .cli.checkout import checkout
from .cli.verify import verify
from .cli.push import push
from .cli.install import install
from .cli.find import find
from .cli.reuse import reuse
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
def search_cmd(query: str, top_k: int):
    """Search knowledge objects by goal text (exact substring match)."""
    store = KOLocalStore()
    results = store.search_by_goal(query, top_k=top_k)
    if not results:
        click.echo("No matching knowledge objects found.")
        return
    for ko in results:
        click.echo(f"{ko.id}  {ko.goal[:70]}")


cli.add_command(commit)
cli.add_command(checkout)
cli.add_command(verify)
cli.add_command(push)
cli.add_command(install)
cli.add_command(find)
cli.add_command(reuse)


if __name__ == "__main__":
    cli()

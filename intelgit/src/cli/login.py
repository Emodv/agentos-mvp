import click

from ..core import config
from ..core.registry_client import RegistryClient


@click.command()
@click.option("--registry", default="https://l2agent-production.up.railway.app", show_default=True)
@click.option("--api-key", default=None, help="Existing API key (skip registration)")
@click.option("--name", default="anonymous", help="Display name for new account")
def login(registry: str, api_key: str, name: str):
    """
    Authenticate with the IntelGit Hub registry.

    If --api-key is provided, saves it directly.
    Otherwise, registers a new account and saves the generated key.
    """
    cfg = config.load()

    if api_key:
        cfg["registry_url"] = registry
        cfg["api_key"] = api_key
        config.save(cfg)
        click.echo(f"Saved API key. Registry: {registry}")
        return

    # Register new account
    client = RegistryClient(registry)
    result = client._request(
        __import__("urllib.request", fromlist=["Request"]).Request(
            f"{registry}/v1/register",
            data=__import__("json").dumps({"display_name": name}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
    )
    if not result or "api_key" not in result:
        click.echo("Registration failed – is the registry reachable?", err=True)
        raise SystemExit(1)

    cfg["registry_url"] = registry
    cfg["api_key"] = result["api_key"]
    config.save(cfg)

    click.echo(f"Registered!  user_id: {result['user_id']}")
    click.echo(f"API key saved to ~/.intelgit/config.json")
    click.echo(f"Credits: {result.get('credits', 1000)}")
    click.echo(f"\nRegistry: {registry}")

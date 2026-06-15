import click

from ..core import config
from ..core.registry_client import RegistryClient
from ..core.store import KOLocalStore


@click.command()
def status():
    """Show local store state and registry connection status."""
    cfg = config.load()
    store = KOLocalStore()
    kos = store.list_all(limit=9999)

    click.echo(f"Local store:  {len(kos)} KOs  (~/.intelgit/)")
    click.echo(f"DID:          {cfg.get('signer_did') or '(not set – run ko config init-identity)'}")

    url = cfg.get("registry_url") or "https://l2agent-production.up.railway.app"
    api_key = cfg.get("api_key")
    click.echo(f"\nRegistry:     {url}")
    click.echo(f"Auth:         {'configured' if api_key else 'not configured (run ko login)'}")

    # Check connectivity
    client = RegistryClient(url, timeout=4)
    result = client._request(__import__("urllib.request", fromlist=["Request"]).Request(f"{url}/health"))
    if result and result.get("status") == "ok":
        click.echo("Connection:   online ✓")
    else:
        click.echo("Connection:   offline (registry unreachable)")

    # Unpushed KOs (those not found in registry)
    click.echo(f"\nRun `ko push --all` to publish all local KOs to the registry.")


@click.command()
def whoami():
    """Show current identity and registry account info."""
    cfg = config.load()
    did = cfg.get("signer_did")
    click.echo(f"DID: {did or '(none – run ko config init-identity)'}")

    url = cfg.get("registry_url") or "https://l2agent-production.up.railway.app"
    api_key = cfg.get("api_key")
    if not api_key:
        click.echo("Not logged in. Run: ko login")
        return

    from ..core.registry_client import RegistryClient
    import urllib.request
    client = RegistryClient(url)
    req = urllib.request.Request(
        f"{url}/v1/whoami",
        headers={"X-API-Key": api_key},
    )
    result = client._request(req)
    if result:
        click.echo(f"User ID:  {result.get('user_id')}")
        click.echo(f"Name:     {result.get('display_name')}")
        click.echo(f"Credits:  {result.get('credits')}")
        click.echo(f"Registry: {url}")
    else:
        click.echo("Could not reach registry.")


@click.command()
def balance():
    """Show credit balance on the registry."""
    cfg = config.load()
    url = cfg.get("registry_url") or "https://l2agent-production.up.railway.app"
    api_key = cfg.get("api_key")
    if not api_key:
        click.echo("Not logged in. Run: ko login")
        return

    from ..core.registry_client import RegistryClient
    import urllib.request
    client = RegistryClient(url)
    req = urllib.request.Request(f"{url}/v1/balance", headers={"X-API-Key": api_key})
    result = client._request(req)
    if result:
        click.echo(f"Credits: {result.get('balance_credits', 0)}")
    else:
        click.echo("Could not reach registry.")

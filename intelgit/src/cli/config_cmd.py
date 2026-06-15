import click

from ..core import config


@click.group(name="config")
def config_cmd():
    """Read and write IntelGit configuration."""


@config_cmd.command(name="get")
@click.argument("key")
def config_get(key: str):
    """Get a config value."""
    val = config.get(key)
    if val is None:
        click.echo(f"{key} is not set")
    else:
        # Never print the private key
        if "private_key" in key.lower():
            click.echo(f"{key} = <redacted>")
        else:
            click.echo(f"{key} = {val}")


@config_cmd.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a config value."""
    config.set_value(key, value)
    click.echo(f"Set {key}.")


@config_cmd.command(name="show")
def config_show():
    """Show all config values."""
    cfg = config.load()
    for k, v in cfg.items():
        if "private_key" in k.lower() and v:
            click.echo(f"  {k} = <redacted>")
        else:
            click.echo(f"  {k} = {v}")


@config_cmd.command(name="init-identity")
def config_init_identity():
    """Generate and persist a new DID:key identity."""
    did, _ = config.get_or_create_identity()
    click.echo(f"DID: {did}")
    click.echo("Identity saved to ~/.intelgit/config.json")

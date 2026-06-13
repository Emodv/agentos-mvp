import click


@click.command()
@click.argument("package")
def install(package: str):
    """Install a knowledge package from the registry (coming soon)."""
    click.echo(f"Registry support is on the roadmap.")
    click.echo(f"Package '{package}' cannot be installed yet.")

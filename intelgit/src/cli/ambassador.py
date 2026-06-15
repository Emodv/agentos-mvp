"""ko ambassador – thin CLI wrapper around scripts/sales_agent.py."""
import subprocess
import sys
from pathlib import Path

import click


@click.command()
@click.option("--dry-run", is_flag=True, default=True,
              help="Preview actions without sending (default: on)")
@click.option("--interactive", is_flag=True, default=False,
              help="Approve each action interactively")
@click.option("--max-per-day", default=20, show_default=True)
@click.option("--channels", default="all", show_default=True,
              help="Comma-separated: github,reddit,twitter,prs,all")
@click.option("--stats", is_flag=True, default=False, help="Show outreach stats")
def ambassador(dry_run: bool, interactive: bool, max_per_day: int,
               channels: str, stats: bool):
    """
    AI outreach ambassador – find agent developers and pitch IntelGit.

    Scans GitHub, Reddit, and Twitter for AI agent developers.
    All actions are previewed first (--dry-run is on by default).
    Set GITHUB_TOKEN, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET env vars.

    Example:
        ko ambassador --dry-run          # preview
        ko ambassador --interactive      # approve each action
        ko ambassador --channels github  # GitHub only
    """
    script = Path(__file__).parent.parent.parent / "scripts" / "sales_agent.py"
    if not script.exists():
        click.echo(f"Sales agent script not found: {script}", err=True)
        raise SystemExit(1)

    cmd = [sys.executable, str(script)]
    if dry_run and not interactive:
        cmd.append("--dry-run")
    if interactive:
        cmd.append("--interactive")
    if stats:
        cmd.append("--stats")
    cmd += ["--max-per-day", str(max_per_day)]
    cmd += ["--channels"] + channels.split(",")

    subprocess.run(cmd, check=False)

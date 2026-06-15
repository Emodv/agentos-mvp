import json
import os

import click

from ..core.executor import execute_and_commit
from ..core.store import KOLocalStore


@click.command()
@click.option("--goal", prompt="Goal", help="What task to perform")
@click.option("--inputs", default="{}", help="JSON string of inputs")
@click.option("--model", default="gpt-4-turbo", show_default=True)
@click.option("--license", "license_", default="reuse-with-attribution", show_default=True)
def commit(goal: str, inputs: str, model: str, license_: str):
    """Commit a new knowledge object by running an LLM and capturing proof."""
    try:
        inputs_dict = json.loads(inputs)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"inputs must be valid JSON: {exc}", param_hint="--inputs")

    click.echo(f"Running model {model} …")
    store = KOLocalStore()
    ko, output = execute_and_commit(goal, inputs_dict, model=model, store=store)
    ko.license = license_
    store.put(ko)  # update with license

    click.echo(f"\nCommitted: {ko.id}")
    click.echo(f"Output hash (sha3-256): {ko.output_hash}")
    click.echo(f"Latency: {ko.latency_ms} ms  Cost: ${ko.cost_usd:.6f}")
    click.echo(f"\nOutput:\n{output}")
    click.echo(f"\nUse `ko checkout {ko.id}` to retrieve metadata.")
